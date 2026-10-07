# OPS-01C 主匹配所有物理请求接入持久账目 — 实施记录（传智杯19）— 2026-10-07

基线 `a6ac549`（OPS-01B 已于 `37133e5` 阶段签收）。本轮零 Git 提交、零推送；未触碰 .env、业务库、closure/public 服务、其他 provider/attempt service/模型/0016/核验链/P2 stash；无真实模型调用、无外发、无依赖安装、无历史清理。本轮实际使用 Start Plan 免费 Flash / 最高推理。

## 交付文件（本轮唯一写入，sha256）

| 文件 | sha256 |
| --- | --- |
| `backend/app/agents/evidence_workflow.py` | 2719e41a2fbdda380d8dfaae7f1490869873630863f06572035da8b4d494809b |
| `backend/app/services/analysis.py` | 7969fbb7f94204449ab0c21f087ee12545b0588b8cc14a1b9019c47f40d43f15 |
| `backend/app/services/report_history.py` | 5e9b1ea2fee4d7ea720c828d9a8832975544de07985c58da3a8a3fbc8238175c |
| `backend/app/tests/test_durable_matching.py`（新增） | b19731e753e042328613c3d84b136eea3f95d1854e63e0ee79761b7214568c34 |
| `backend/app/tests/test_real_matching.py`（仅 fake_workflow 签名加 `durable_observer_factory=None`） | d77dceea396a38e81cb5f53a40241dbd2d68b6a6e6fd9cbf5ff975fcd6df264d |
| `backend/app/tests/test_report_history.py`（仅 5 处 `prepare_history_tool` 调用补 `session_factory=factory`） | cc5af15002d55cc74fae7e810182a113adcbc83c111bef48ebb45c6fd4a8575a |

未动核验链 `ai_request_attempts.py`/`application_verification.py`（接口原样复用 AttemptContext/AttemptService/DurableRequestObserver，无跨模块反向 import）。`docs/当前接力.md` 的一处空白行差异为本轮之前既有工作区状态，未触碰。

## 实现（对照任务卡）

1. `run_evidence_workflow` 新增可选 `durable_observer_factory(provider, step)`；规划每轮 `planning_{N}`、分析 `analysis`、定向修正 `repair` 调用前安装 observer，物理重试沿用 provider 既有 prepare/mark_intent/receive；未传参的离线/旧调用 API 不变。
2. `execute_match_task` 服务端绑定 task_id/created_by/run_token；`_matching_observer_factory` 每 step 建 AttemptService，同一 run 跨 step 共享 physical_sequence（run_token 维度）。仅当外部 provider 实际安装 observer（`ledger.installed`）才视为 durable；rules/mock/未调用 provider 的兼容路径零伪造 attempt。
3. 每次发送前 authorize 回调新鲜复核：owner 活跃+学生角色、任务固定 job/materials/consent/jobId/candidateId 未被替换、冻结材料版本仍属本人且 versionNumber/contentHash 未变（`_materials_still_frozen`）。配合 AttemptService 既有 claim/token/consent 检查；旧 run 仍 finish_task CAS、不发布报告。
4. HTTP 前主 session `await session.commit()` 释放预算检查的 creator 行锁；`prepare_history_tool` 改为必填 `session_factory` 短独立 session 读 MatchItem，返回即释放，不依赖下一进度文字提交；同 owner/岗位/提交前固定 report、历史非当前证据边界全部保留。
5. 结清仿核验链 bounded(5s)+shield 独立 book：workflow 结束（成功/fallback/解析或引用校验失败）、异常、取消、报告保存失败各出口都 reconcile；失败保留 received_unbooked 并记日志缺口，不重发 HTTP；book 与业务 finish/report 事务完全分离。
6. 新 mode 报告 `usage/usageKnown/usageBooked/attemptSummary` 来自持久 summary；零可信收据时 usage=None（不展示伪零总量，AgentStep 的 inputTokens/outputTokens/latencyMs 同样置 None）；新模式绝对停止原 finalize 聚合 AiUsageLog 写入；旧模式路径与历史行不变（回归 81+1028 全过佐证）。

## 命令与退出码（backend/，venv `./.venv/Scripts/python.exe`；PG URL 已脱敏）

```
ruff check app/tests/test_durable_matching.py app/services/analysis.py app/services/report_history.py app/agents/evidence_workflow.py   # exit 0
ruff check app                                                                                                                          # exit 0
python -u -m pytest app/tests/test_durable_matching.py -q --tb=short -p no:cacheprovider --basetemp=...            # SQLite / PG
python -u -m pytest app/tests/test_real_matching.py app/tests/test_ai_evidence_workflow.py app/tests/test_report_input_budget.py app/tests/test_report_history.py -q ...   # 受影响回归
python -u -m pytest app/tests -q -p no:cacheprovider --basetemp=D:/jbcode/tmp/pytest-ops01c-full-{sqlite,pg}       # 全后端
PG 运行加 CAREERPROOF_TEST_DATABASE_URL='postgresql+asyncpg://<redacted-local-test-pg>'
```

| 运行 | 原始日志 | 结果 | 退出码 | sha256（前16） |
| --- | --- | --- | --- | --- |
| 红测试（实现前，SQLite） | red-sqlite-first.raw.out | 1 failed：3 次物理 HTTP、0 attempt 行 | 1 | 09204a0f3f75eea2 |
| 主用例首轮绿（SQLite） | green-sqlite-attempt2.raw.out | 1 passed | 0 | 4d2562a7b521fe0f |
| （测试笔误轮） | green-sqlite-attempt1.raw.out / full-sqlite-attempt1.raw.out | 字段名/查询范围/登录态三处测试构造错误，均独立留档未覆盖 | 1 | e1b5034c43ba3aa8 / accfa8e1109759b0 |
| 新文件全量 SQLite | full-sqlite-attempt2.raw.out | 6 passed, 1 skipped（PG 探针按条件跳过） | 0 | 152a147c37a615b8 |
| 新文件全量 PG | full-pg-attempt1.raw.out | **7 passed, 0 skipped（含锁探针）** | 0 | 1b353231b309695e |
| 受影响回归 SQLite | regression-sqlite-attempt1.raw.out | 81 passed | 0 | b8750bf5c8322fac |
| 受影响回归 PG | regression-pg-attempt1.raw.out | 81 passed | 0 | 931f04404d16627e |
| 全后端 SQLite（终态） | full-backend-sqlite.raw.out | 991 passed, 37 skipped | 0 | 7f2167f82ec3a463 |
| 全后端 PG（终态） | full-backend-pg.raw.out | **1028 passed, 0 skipped** | 0 | e064281d4c669294 |

每次失败均有独立 `.raw.out`，未覆盖任何历史日志。运行前后 compose PG `cp_test_*` schema 恒为既有 3 个，本轮专属 schema（`current_schema()`+逐表 namespace 断言，`create_all(checkfirst=False)`）自建自清；本轮 `.tmp-ops01c-*` basetemp 已清理。

## 终态验证要点（主用例 + PG 探针）

- 合成 DeepSeekProvider+MockTransport 全链路（注册→岗位→上传→真实解析→匹配→后台 execute_match_task）：analysis 首物理请求 429 且错误体带可信 usage → 照实记账；重试 200 引用冲突 → 定向修正一次成功；每个物理 attempt 的身份（task/owner/run_token/provider/model）、step 标签、physical_sequence 连续、可信账目恰好一次（ledger request_seq=attempt physical_sequence，attempt_id 非空）。
- usage_unknown（503 无 usage）保持 unknown 不双记；usageKnown=False 时不展示伪零总量；usageBooked=True。
- fallback（修复仍引用违规）仍结清已持久收据，rules 报告照常保存；booking 失败恢复 0 额外 HTTP，received_unbooked 可由独立 reconcile 幂等补记；报告保存失败（asdict 注入）→ 任务 FAILED、账目已 booked、无报告发布。
- owner 停用：prepare 拒绝 → 0 行 0 发送；冻结材料被替换：mark_intent 拒绝 → 恰 1 行 not_sent(reason=send_admission_failed)、0 发送、无账目。
- 并发重复 reconcile 恰好 1 行 ledger（服务级）。
- PG 锁探针：历史读取后、analysis HTTP 阻塞窗口内，本 schema 所有关系 `pg_locks.granted` 为 0 —— 历史短 session 与主 session 均已释放；未删除任何授权检查。

## 自审

- 红测试先行（3 HTTP / 0 attempt），实现后同一用例转绿；三处失败轮全部是测试自身构造错误（attempt 字段名、任务查询缺 task_type 过滤、停用后不能再用学生登录态轮询 API），实现断言只增未减。
- durable 判定以"实际安装 observer"为准，不是配置名；旧聚合写入仅 durable_summary 为 None 时执行，legacy 回归与旧 ledger 行为（320 输入账目行等）逐项保持。
- 授权复核在 mark_intent 事务内、与 _live_identity 同锁串行；`usageAccountingMode` 由 AttemptService.prepare 自行写入快照，authorize 只比对五个冻结键，不受其影响。
- 结清 wait_for(5s)+shield+done-callback 记日志；取消路径吞掉的是"结清期间到来的二次取消"，随后重抛原 CancelledError。
- 循环 import 未引入：analysis → ai_request_attempts 单向；未从 application_verification 拷贝任何运行时依赖，仅复刻 bounded/shield 模式。

## 未验证项 / 边界（如实陈述）

- 取消窗口的实际 CancelledError 路径未做进程级硬停注入（OPS-01B 已对核验链做过四窗口硬停；主匹配链未在本轮复刻 TerminateProcess 级验证），取消结清逻辑靠代码路径与幂等 reconcile 保障，建议 Codex 风险审查评估是否补做。
- 共用日预留与跨午夜批次仍是下一批：本批通过不构成"两链统一日预算已完成"；工作流内 per-report 预算仍用 provider 内存 combined_usage 口径，日预算检查仍在 claim 时点读 AiUsageLog 聚合。
- SQLite 默认路径下 PG 锁探针按条件跳过（已在 PG 终态运行 0 跳过通过）。
- `attemptSummary`/`usageBooked`/`usageKnown` 目前只入 analysis_metadata（DB），MatchReportView API 未新增暴露字段；如需前端展示需另行小批量（超出本卡写入范围）。

## 交棒

本轮终态。后续 Codex 只读全文风险审查并独立复跑最高风险项（建议：PG 锁探针 `test_history_read_releases_borrowed_transaction_during_http` 或 owner 停用 0 发送用例）；Codex 不修改上述六个文件、不与本轮数据库测试并行。交棒后本轮停止写入。
