# Codex 关键修正合规核验（rev2，随事件门控修订更新）

2026-10-09。rev2：按交棒指示把同步点改为"胜方取得原身份锁后暂等败方登记事件"；rev1 的"锁前双方注册同步"已废弃（其满足有界注册等待，但锁前同步非必需）。核验对象 `test_ai_budget_production_race.py`（SHA-256 `1daf8b1b3506616532695765d9c14644415ceeaa4d2aebb9d5a6376d8d62dd32`）。

## 修正条款 → 代码映射（行号为 rev2 文件）

| 修正条款 | 实现位置与事实 |
|---|---|
| 双方事件屏障设在 prepare_for_send 进入原函数之前 | `prepare_wrapper` L166-176：双方到齐 `both_arrived` 才放行进 `original_prepare`（L176）；屏障在原函数外、入口预检事务已 commit 之后。 |
| 胜方完全由真实锁竞争决定，不用 sleep 猜先后 | 锁前**零同步**：每方登记 backend pid（L193，登记仅需 `SELECT pg_backend_pid()`，不涉及行锁）后**立即**调用原 `_live_identity`（L197）；谁先取得 owner User 的 FOR NO KEY UPDATE 谁是胜方。 |
| 胜方取得原身份锁后暂等；败方进入 _live_identity 前登记 session 并通知胜方，再实际调用原锁 | 败方登记即置 `both_registered`（L196，即"通知"）；胜方在原 `_live_identity` 返回（持锁）后以 `both_registered` 事件作门（L203-212，有界 OVERLAP_TIMEOUT_SECONDS=15），随后才继续原 reserve/commit。 |
| 两方必须在胜方 commit 前都已进入原 prepare、创建独立 session | 胜方 reserve/commit 被登记事件门控：事件置位 ⇔ 双方 prepare session 均已创建并进入 `_live_identity` 包装层（包装层就在原 prepare 事务内）。 |
| 不得等胜方 prepared/commit 后才放行败方（那只是先后准入） | 双方同时离开 prepare 入口屏障，败方自主推进（登记→原锁尝试），其推进不被胜方任何阶段门控；胜方的等待发生在自己仍处 prepare 事务内（reserve 之前），不是对败方的放行条件。 |
| 原身份/事务/锁不得 commit/跳过/改写 | 仅包装 `prepare_for_send` 与 `_live_identity`（L220-221），包装内无 commit/跳过/改写；`SharedBudgetService.reserve` 与准入逻辑从未 patch、未 mock。 |
| 败方自然数据库锁等待后拒绝 | 败方对同一 User 行的原锁 SELECT 在 PG 内真实等待；胜方 commit 释放后败方继续原路径，`reserve` 读到已提交 hold → `daily_report_limit` 真实拒绝。 |
| 第三 session NOWAIT 在真实 HTTP 阻塞时检查 | 用例顺序：`harness.overlap` → `gate.entered`（MockTransport 真阻塞）→ 败方完成拒绝 → User/AiDailyBudget/Task 严格单发 NOWAIT（未知锁即失败）→ 才 `release`。 |

## 无人工死锁论证（rev2）

胜方持 User 锁等待的仅是"败方登记"事件；败方登记只需新 session + `SELECT pg_backend_pid()`，不需要胜方持有的任何锁，故败方总能到达。除胜方这一等待外，双方之间无任何锁后同步；`pg_blocking_pids`（L233）只作目录观测证据（观测节奏含 0.01s 间隔，但不决定任何先后——先后由真实锁取得与登记事件决定）。若败方链路提前死亡，15 秒有界超时带时间线 fail。

## 附带登记：匹配链偶发第二次物理调用观察

`full-file-sqlite-final-20261009b.raw.out`（哈希 `f7d1dc663a43d744160ae4d189574d86761eba19bab6d82dcaa99ee8b1d08d16`，已留存）记录一次离线契约用例中匹配链发出 **2** 次 chat/completions POST（该轮 instrumentation 尚未就位，第二次调用的类别未及分类；此后 21 次复跑均为 1 次 analysis，正常路径分类证据见 `offline-contract-20261009c-run{1,2,3}.raw.out` 的 `RACE-EVIDENCE offline-single-chain {"httpCalls": 1, "httpSteps": ["analysis"]}`）。可能成因是规则分析输出偶发触发 planning 步（其资格取决于解析器产物）或一次 repair，属链路自身行为，非本测试编排引入（该用例不安装任何 harness 包装）。已按"逐物理收据恰结算一次/恰一行账目、reconcile 复跑为 0"加固断言，使测试不再依赖调用次数恰为 1；此观察交棒 Codex 判断是否需要生产侧跟进。
