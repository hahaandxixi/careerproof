# B-08 实现自审（review-agent，只读）

审查范围：`backend/app/agents/provider.py`、`backend/app/models/analysis.py`、
`backend/app/services/analysis.py`、`backend/app/services/application_verification.py`（工作区改动 vs HEAD 1cdb506），
新增 `backend/alembic/versions/0013_ai_usage_idempotency.py`、`backend/app/tests/test_b08_usage_accounting.py`。
明确排除（他任务所有）：`app/services/applications.py`、`app/tests/test_applications_api.py`、docs/*。

## 结论

无 P0/P1/P2 发现。两项 P3 备忘（均不阻塞验收）：

[P3] 入账失败时快照无已入账标记 — app/services/application_verification.py:612-624
入账（`_book_usage_decoupled`）失败仅记服务端日志，收尾快照仍写 `usageKnown=true`。
`usageKnown` 语义是"响应携带可信 usage"（诚实），快照并未声称"已入账"，未违反任务卡
"异常不得伪装为已入账"；但账务对账方无法从快照区分已落账与已记录缺口，只能翻日志。
`_book_usage_decoupled` docstring 已把该缺口声明为"仅外部对账可弥合的已知未入账间隙"，
与任务卡第 6 条"只记录该局限"一致。若后续要对账自动化，可考虑在快照补 `usageBooked` 标记
（属扩权，本卡不做）。

[P3] `_non_negative_int` 对字符串/浮点宽松 — app/agents/provider.py:564-572
`int("123")` 会接受数字字符串、`int(5.7)` 会截断为 5，严格说宽于任务卡"非负整数"措辞；
但与改动前 `int(usage.get(...) or 0)` 的宽松度一致，非本次引入的回归，且 DeepSeek 实际
返回整型。不修。

## 已核查项（均通过）

- 幂等键：`(run_token, request_seq)` 部分唯一索引在模型 `__table_args__` 与迁移 0013 中
  同名同谓词（SQLite/PG 双方言 `WHERE run_token IS NOT NULL`），metadata 与迁移无漂移；
  旧行 run_token 为 NULL 不受约束，实测重复插入被拒、NULL 行豁免、旧 48 行（PG 实库）无损。
- 取消期间实际提交：入账走独立 session + `asyncio.shield` + 5 秒有界等待；响应返回后到
  shield 之间无其他 await（`validate_verification` 为同步），取消注入点只会命中 shield，
  已开始的 commit 不会被外层取消中断；`usage_persisted_seq` 仅在 commit 成功后推进，
  失败重试依赖 ON CONFLICT 幂等。
- 撤回不落结论：收尾前 `_authorized(lock=True)` 复检抛 AppError → `failure=authorization_revoked`、
  `analysis=None`；租约失效/取消用例均断言快照无 analysis。撤回语义由既有
  `test_withdrawal_*` 用例覆盖（45 通过含其中）。
- 预算 distinct：仅把 `count(行)` 换成 `count(distinct analysis_task_id)`，join 与
  created_by/日期过滤未动；其他工作流一行一任务，计数不变。
- provider：`get_ai_provider()` 每次新建实例，`usage_records`/`request_seq` 无跨任务累积；
  4 处 `_capture_usage` 调用点均为每真实响应恰好一次；`_max_attempts=1` 在验证流固定，
  不存在重试重发已撤回片段的路径。
- 测试缺口说明：取消用例依赖测试内 `reap()` 复刻 `recover_interrupted_tasks` 的收租行为，
  属测试侧复制生产逻辑，若收租逻辑变化需同步（既有测试模式的延续，非新增风险）。

## 验证结果（详见同目录各 log）

SQLite 定向 7/7、SQLite 相邻回归 45 通过/5 跳过、PG 隔离定向 7/7、PG 隔离 verification
42/42、Ruff 通过、后端全量 823 通过/24 跳过；迁移在 PG 实库无损升级至 0013、SQLite 上
0013 DDL 单独验证通过。全链 alembic 不支持 SQLite（0001 起 CREATE EXTENSION vector），
属既有约束。
