# B-08 调查：已发生模型用量与任务租约解耦的幂等入账方案（v2，按 Codex 审计修订）

基线：嵌套仓库 HEAD `1cdb506`，只读调查 + 只读运行现有定向测试，未改任何生产代码。
v2 修订：①可信 usage 判定前置到 HTTP 响应处；②reportCount 改 distinct；③幂等键改用既有
`run_token + request_seq`；④CancelledError 路径写清独立 session/shield/失败处理，删除无唯一
约束的查重方案。待 Codex 决策问题见 §6。

## 1. 现状与丢账/重复账路径（代码定位）

- `application_verification.py:560-610`：`AiUsageLog`、`AgentStep`、`input_snapshot.usage` 全部
  嵌在 `if await finish_task(...)` 为真分支内，最后 `session.commit()`（610 行）；`finish_task`
  （`task_lifecycle.py:46-74`）是 `(id, RUNNING, run_token)` CAS 且不提交。丢账窗口：
  ①调用期间心跳失效或停机取消（`CancelledError` 是 BaseException，`except Exception` 不捕，
  收尾整段不执行）→ finish False → 用量丢弃，任务由 `recover_interrupted_tasks`（163-217 行）
  收割 FAILED；②finish 为真但 610 行 commit 失败 → 整事务回滚同丢。
- **usage 事实在捕获处即失真**：`provider.py:548-561` `_capture_usage` 对 `payload["usage"]`
  缺失/非 dict 时折叠为 `{}`，仍生成**零值 ModelUsage 并 append 进 `request_usages`**——因此
  "`request_usages` 非空"不等于"收到可信 usage"；零值占位与"服务端真实报 0"在现有结构中不可区分。
- 同构问题：`analysis.py:646-648`（finish 失败即 `rollback()` 丢 `usage_record`）、
  `visual_evidence.py:258`、`career_planning.py:644`、`job_drafting.py:150`（本卡只设计）。
- 现有测试覆盖：租约 CAS `test_material_tasks.py:85-98`、收割 `:121`、撤回保用量走 finish
  成功分支 `test_application_verification.py:428`；**finish 失败分支与 usage 真实性判定零覆盖**。
  定向现有测试实测：SQLite 45P/5S、PG(cp_test_*) 42P，退出码均 0（tests.log）。

## 2. 三状态的入账与展示语义（任务卡第 4 条；判定前置到 HTTP 响应处）

| 状态 | 判定 | 入账 | 展示 |
| --- | --- | --- | --- |
| 响应含**有效 usage 对象** | `_capture_usage` 处显式记录 `usage_present`：`usage` 为 dict 且 `prompt_tokens`/`completion_tokens`/`cached_tokens` 可解析为非负整数（对象存在即可信，**不以 tokens>0 为准**，避免把全缓存命中误判为缺失） | 账本行（可信用量），键 `(run_token, request_seq)` | 任务详情 `usage` 照旧；日预算计入 |
| 请求完成但 usage 缺失/无效 | 现被折叠为零值占位（provider.py:552-557）；实现卡需在此分流 | **账本不记可信用量**；是否写 `estimated=true` 估算行待 §6-b 决策 | 任务展示"外部调用已发生，账单未知" |
| 请求未完成（超时/连接失败/取消） | 无响应 | 无账单事实；同上 | 现有 failureKind 展示 |

实现卡需给 provider 增加每请求的 `usage_present`/`request_seq` 元数据（现只有零值合并结果）。

## 3. 事务边界与幂等设计（需迁移；按任务卡第 10 条先审后做）

- **关键改动**：usage 在 provider 响应捕获处**立即独立短事务**落账（先记账后校验/收尾），
  收尾事务不再写 usage；窗口缩至"响应接收→短事务提交"（毫秒级，进程崩溃不可消除，如实标注）。
- **幂等键 = `(run_token, request_seq)`**（v2：放弃 attempt 数字方案）：
  - `run_token`：每次 claim 生成的 uuid4（`task_lifecycle.py:25`），全局唯一，精确锚定"哪一次
    执行"；finish/收割会把任务行 run_token 置 NULL，但账本行存**值拷贝**，不受影响；无需读任务行
    即可赋键，避免收割/再认领后 attempt 归属歧义。
  - `request_seq`：provider 实例内按**每次真实发出的 HTTP 请求**从 1 递增（含响应缺 usage 的
    请求——占号但无账单行）。仅内存累计：进程崩溃后重试必是新 claim/新 run_token，键空间不重叠。
    verification 设 `_max_attempts=1`（application_verification.py:506）单请求任务恒 seq=1。
  - 唯一性：`ai_usage_logs` 增 nullable `run_token`、`request_seq` 两列 + 部分唯一索引
    `(run_token, request_seq) WHERE run_token IS NOT NULL`（PG/SQLite 均支持部分索引；旧行 NULL
    豁免，0001_initial 后追加 alembic revision）。写入 `INSERT ... ON CONFLICT DO NOTHING`。
- **无唯一键即无诚实幂等**：v1 的"写前 SELECT 查重"过渡方案**删除**（查重-插入间存在 TOCTOU，
  不得冒充幂等）；实现卡以迁移为前提。
- **CancelledError 路径**：①记账用 `async_session_factory()` **新开独立 session/短事务**，绝不复用
  已被取消的请求 session（其事务可能失效）；②`asyncio.shield(记账协程)` 包裹并内置短超时
  （如 5s），防外层取消中断已开始的记账、也防取消悬挂；③shield 内事务失败（瞬断）→ 记
  `log(exc_info)` 后放弃并传播取消——该次用量为"事实已知未入账"缺口，同步设计只能缩小不能消除，
  对账以外部账单为准；不引入无界的重试/补偿队列（超出最小改动，如需见 §6-e）。
- **日预算（`analysis.py:136-160`，行级锁 + created_at 求和）**：v2 修订——`reportCount` 须从
  `count(AiUsageLog.id)` 改为 **`COUNT(DISTINCT AiUsageLog.analysis_task_id)`**，否则"每真实请求
  一行"后多请求任务虚增报告数；`input/output_tokens` 仍逐行 `SUM`。
  **取消任务消耗计入预算**：现查询无 status 过滤，凡已写入的行一律计入（撤回后 CANCELLED 的
  已发生消耗计入，与现有 `:428` 语义一致，符合不变量"日预算计入已知真实消耗"）；未收到 usage
  的调用无行不计入——账面偏低是保守方向。

## 4. 故障注入测试点（设计，不实现）

1. **租约失效丢账**：provider 返回有效 usage 后、finish 前强制租约失效（`task_lease_seconds=0`
   或改 `run_token`/置 FAILED 模拟收割）→ `AiUsageLog` 恰 1 行（含当时 run_token 值、seq=1）；
   任务终态 FAILED；投递不重开放、analysis 不落库（`:428` 语义不回退）。
2. **收尾 commit 失败**：monkeypatch `session.commit` 在收尾处抛一次 → usage 已因"响应后即记账"
   存在恰 1 行；任务留 RUNNING 后收割 FAILED；owner 重试 → 新 claim/新 run_token，新调用成新行。
3. **重复收尾/重复记账**：同 token 二次 finish + 同 `(run_token, request_seq)` 二次插入 →
   仍恰 1 行（CAS + 唯一键双保险，叠加 `test_material_tasks.py:85-98`）。
4. **停机取消**：响应后注入 `CancelledError` → shield 内短事务完成 → 恰 1 行；任务收割 FAILED；
   撤回投递不保存结论。
5. **usage 缺失响应**：响应无 usage 字段 → 无账单行（或按 §6-b 写 estimated 行且预算查询排除）；
   同 attempt 内重发请求 seq 递增、键不冲突。
6. **预算口径**：多请求任务 reportCount=1（DISTINCT）；取消任务已写入的行计入预算；
   估算行（若采纳）被预算查询排除。
7. **预算串行化不回退**：响应后即记账时并发预算检查仍串行（参照
   `test_visual_postgres_concurrency.py` 的 `pg_blocking_pids` 证明模式）。

## 5. 跨角色授权影响与只能保守估计的事项

- 授权影响：记账不新增用户可见面；`AiUsageLog` 仅入日预算统计；撤回/越权路径行为不变
  （`_authorized` 复查与 `authorization_revoked`/`snapshot_changed` 分支不动）。
- 只能保守估计：①"请求已发出未收到 usage"的真实成本（只能按 `max_tokens` 上限估，是否落估算
  行待 §6-b）；②毫秒级残余窗口的丢失概率；③shield 内短事务仍失败时的缺口只能事后对账。
- 迁移涉及 `ai_usage_logs` 两列 + 部分唯一索引 + alembic revision；同构服务是否一并改造见 §6-f。

## 6. 仍需 Codex 决策的问题

- **a. usage 有效性判定**：建议"对象存在且字段可解析为非负整数即可信"（全缓存命中 tokens=0 不
  误判为缺失）；是否接受？
- **b. 估算行**：缺 usage/未完成请求是否写 `estimated=true` 行入 `ai_usage_logs`（需再加一列），
  还是仅任务日志留痕、账本不写？若写，预算查询需排除，`reportCount` 是否排除同议。
- **c. reportCount 口径**：改 `COUNT(DISTINCT analysis_task_id)` 是否批准（现状每任务一行时两
  口径相等，改为逐请求行后必需）。
- **d. 取消任务消耗计入预算**：确认"已入账行计入（含 CANCELLED）"是期望语义（现行为即如此）。
- **e. 记账短事务失败的兜底**：默认仅日志 + 人工对账；是否需要异步补偿/重试（超出最小改动）。
- **f. 改造范围**：application_verification 单点先行，还是四个同构服务（analysis/visual_evidence/
  career_planning/job_drafting）同卡统一改造。

## 测试证据

- [tests.log](tests.log)：只读运行现有定向用例的原始命令、完整输出与退出码（SQLite：
  test_material_tasks + test_application_verification，45 passed/5 skipped，exit 0；PostgreSQL
  cp_test_* 隔离 schema：test_application_verification，42 passed，exit 0）。
- 未验证项：§4 故障注入测试点均为设计（未实现未运行）；生产代码零改动；未真实调用 DeepSeek。
