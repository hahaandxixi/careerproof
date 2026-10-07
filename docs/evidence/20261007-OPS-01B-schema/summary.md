# OPS-01B 模型与 0016 迁移交棒（ZCode，2026-10-07）

起点 HEAD 06519f5。本阶段只交付模型/迁移/对应测试；核验链与 goal 未完成。原始命令、退出码、过程中失败见 `commands.md`，hash 见 `hash.txt`，日志为本目录 `red-sqlite.log`、`green-*.log`、`ruff.log`。

## 已就绪内容

- **模型**：`app/models/ai_request_attempt.py` 新增 `AiRequestAttempt`（表 `ai_request_attempts`，UUID/Timestamp mixin），字段严格按任务卡契约：`(run_token, physical_sequence)` 唯一（命名 `uq_ai_request_attempts_run_token_physical_sequence`）、`state` CHECK 限 5 态（默认 `not_sent`，server_default 同）、`physical_sequence>0`、token/延迟非负 CHECK（NULL 豁免）、`usage_raw` JSON 非空 server_default `'{}'`。已注册进 `app/models/__init__.py`。
- **ledger 链接**：`AiUsageLog.attempt_id` UUID 可空，具名 FK `fk_ai_usage_logs_attempt_id` → `ai_request_attempts.id` ON DELETE RESTRICT；唯一索引 `uq_ai_usage_logs_attempt_id`（普通唯一索引，SQLite/PG 均允许多 NULL 行，实测旧行兼容）。
- **0016**：`down_revision="0015_growth_answer_drafts"`；无新数据库 Enum 类型（PG 已断言 `pg_type` 无 attempt 相关 enum）。**降级守卫**：除 `booked` 与 `not_sent AND ended_at IS NOT NULL` 外任何状态 raise `RuntimeError`（消息含状态计数），SQLite/PG 实测 `in_flight`/`received_unbooked`/`usage_unknown`/未结束 `not_sent` 均拒绝且表与列原样保留；`booked` 与已结束 `not_sent` 可降级。实现细节：ledger 加/删 `attempt_id` 走 `batch_alter_table`（SQLite 无法 ALTER 加具名 FK；batch 拷贝会反射保留旧 `run_token` 部分唯一索引谓词，已实证 `sqlite_where` 被保留），其余方言为普通 ALTER。降级顺序：先删新索引 → 列 → attempt 表。

## Codex 集成要点

- 导入：`from app.models.ai_request_attempt import AiRequestAttempt`（不在 `analysis.py` 里）。
- `provider`/`model` 按契约记为非空（创建时即写入意图值）；若服务层需创建时未知 provider，请回传卡片，我不单方面改 nullability。
- 未结清回退拒绝的异常类型是 `RuntimeError`（SQLite/PG 测试都按此断言）；如服务层要捕获请匹配。
- `analysis_task_id` 按卡未加二级索引（卡只列了两个唯一键）；若核验服务按 task 查询列表，建议在后续卡里显式加。
- 迁移可独立执行验证：`pytest app/tests/test_ai_request_attempt_migration.py`（SQLite 部分）+ `CAREERPROOF_TEST_DATABASE_URL=postgresql+asyncpg://...`（专属 `cp_test_*`，自动建/删随机 schema，禁止回落 public 已内置断言）。

## 测试结果

- SQLite：schema 15/15、迁移 1/1 → 合并 16 passed, 1 skipped（PG 用例跳过），退出码 0。
- 专属 cp_test PG：17 passed，退出码 0；含升降级、FK/具名约束/唯一索引存在性、旧行完整 hash 前后不变（`sha256(sorted(rows))`）、未结清拒绝、RESTRICT 删除拒绝、多 NULL 行兼容。
- Ruff：6 个自有文件全部通过。

## 自审（缺陷优先）

- [P3] `commands.md` 中第 2~5 项过程失败的原始输出因迭代覆盖未留档，只留了首红灯与全部终态日志；失败原因与修复已在 `commands.md` 如实记录。后续证据目录建议每轮失败即另存。
- [P3] `digest()` 用 `repr(sorted(rows))` 做 hash：行内含 Decimal/datetime 的 repr 跨方言可能有细微格式差（本次 SQLite 与 PG 各自前后对比，不跨方言比较，结论成立）；若 Codex 想跨方言对账需换规范化序列化。
- [P3] SQLite 迁移测试中旧行 `cost_rmb` 存为字符串化 NUMERIC，`ledger_rows` 回读值与种子字符串一致，hash 对比成立；但这依赖 SQLite 弱类型，不代表 PG 精度行为（PG 用的是真实 NUMERIC，已独立验证）。
- 无 P0/P1/P2。未发现 model 与 0016 之间的列/约束漂移（对照检查过 22 列、CHECK、唯一键、FK 名称）。

## 边界

未触碰 Codex 的 `services/ai_request_attempts.py`、`services/application_verification.py`、`test_durable_attempt_service.py` 及 provider/receipts；未跑全后端测试；未调用真实模型/外发/重启服务；未使用 `.env`/业务库/`closure`/`public`；未做任何 Git 写操作；未自行切换个人套餐。此交棒后停止所有文件与 fixture 写入。
