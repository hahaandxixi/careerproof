# 命令与退出码记录（2026-10-07，OPS-01B 模型/0016 迁移）

工作目录：`backend/`（Git 根 `D:\jbcode\web ai\jianli`，起始 HEAD 06519f5）。
Python：`./.venv/Scripts/python.exe`。未触碰 `.env`，未提交/推送 Git。

| # | 命令 | 退出码 | 日志 |
| --- | --- | --- | --- |
| 1 | 红灯：`./.venv/Scripts/python.exe -m pytest app/tests/test_ai_request_attempt_schema.py app/tests/test_ai_request_attempt_migration.py -q -p no:cacheprovider --basetemp=./.tmp-ops01b-red`（模型/迁移尚未实现） | 2（预期收集失败：`ImportError: cannot import name 'AiRequestAttempt'`） | `red-sqlite.log` |
| 2 | `pytest app/tests/test_ai_request_attempt_schema.py ...`（实现后，单独跑） | 0（15 passed） | `green-schema-sqlite.log` |
| 3 | `pytest app/tests/test_ai_request_attempt_migration.py ...`（SQLite 部分；PG 用例自动跳过） | 0（1 passed, 1 skipped） | `green-migration-sqlite.log` |
| 4 | `CAREERPROOF_TEST_DATABASE_URL='postgresql+asyncpg://careerproof:careerproof@localhost:5432/careerproof' pytest app/tests/test_ai_request_attempt_migration.py ...`（真实 SQLite + 专属 `cp_test_*` schema） | 0（2 passed） | `green-migration-pg.log` |
| 5 | 终跑（SQLite only，两文件合并）：`pytest app/tests/test_ai_request_attempt_schema.py app/tests/test_ai_request_attempt_migration.py -q -p no:cacheprovider --basetemp=./.tmp-ops01b-final-sqlite` | 0（16 passed, 1 skipped） | `green-final-sqlite.log` |
| 6 | 终跑（含 PG）：同上加 `CAREERPROOF_TEST_DATABASE_URL` 环境变量（内联传入，不用 .env） | 0（17 passed） | `green-final-pg.log` |
| 7 | `./.venv/Scripts/python.exe -m ruff check app/models/ai_request_attempt.py app/models/analysis.py app/models/__init__.py app/tests/test_ai_request_attempt_schema.py app/tests/test_ai_request_attempt_migration.py alembic/versions/0016_ai_request_attempts.py` | 0（All checks passed!） | `ruff.log` |

## 过程中的失败（原文已随迭代被后续日志覆盖，此处如实记录原因与修复）

1. schema 首跑 15 errors：fixture 给 `AnalysisTask(created_by=...)` 传了 User 对象而非 UUID（`'User' object has no attribute 'hex'`）。修复为先 flush user 再用 `user.id`。
2. 0016 SQLite 首跑：`NotImplementedError: No support for ALTER of constraints in SQLite dialect`——Alembic 对 SQLite 不支持以 ALTER 添加具名 FK。修复：ledger 的 `attempt_id` 加列/删列改走 `op.batch_alter_table`（SQLite 走建表拷贝，反射保留部分唯一索引谓词；PG 走普通 ALTER）。已实证 SQLAlchemy 2.0 会反射 `sqlite_where`，部分索引在 batch 重建后保留。
3. 测试自身缺陷：曾把种子旧行链到 attempt 后又在测试中删除该行，导致降级后少一行；改为插入一条新的链接行做 FK 验证。
4. PG 首跑：`InFailedSQLTransactionError: current transaction is aborted`——asyncpg 下 Session 级 `begin_nested()` 回滚失败语句后外层事务仍 aborted（已用最小脚本实证）。修复：改用 `engine.connect()` + 连接级 `connection.begin_nested()`（与本仓库既有 PG 测试模式一致）。
5. PG 二跑：降级后行集合一致但物理行序变化导致等值断言失败；改为排序后比较 + 排序 hash（`digest()` 本身即排序哈希）。

## 边界声明

- 本次实际改动仅：`backend/app/models/ai_request_attempt.py`（新增）、`backend/app/models/analysis.py`（仅 AiUsageLog 增 attempt_id + 唯一索引）、`backend/app/models/__init__.py`（注册）、`backend/alembic/versions/0016_ai_request_attempts.py`（新增）、两个新测试文件、本证据目录。
- `git status` 中同时存在 `backend/app/services/application_verification.py`（M）、`backend/app/services/ai_request_attempts.py`、`backend/app/tests/test_durable_attempt_service.py`（未跟踪）——这些是 Codex 并行工作区文件，本次未读改。
- 未运行全后端测试、未调用 provider/service、未调用真实模型、未外发、未重启服务、未触碰业务库/`closure`/`public`、未做 Git 写操作。
