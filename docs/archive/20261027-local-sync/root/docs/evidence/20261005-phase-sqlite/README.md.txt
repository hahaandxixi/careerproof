# PHASE-CHECK：后端 SQLite 全量与静态检查证据（只读阶段）

- 日期：2026-10-05；基线 HEAD：`9bc9601`（`git rev-parse` 实测一致）
- 范围：仅运行后端测试与静态检查并记录证据；产品/测试/其他证据/正式文档/运行器一律只读。
- 数据库边界：**未连接任何业务库与外部服务**。子进程内移除 `CAREERPROOF_TEST_DATABASE_URL`（父 shell 实测 UNSET，backend/.env 中无该键；本任务未改 .env）。

## 夹具确认（读源码，未运行即确认隔离）

- `backend/app/tests/test_real_matching.py:52` `matching_db`：`CAREERPROOF_TEST_DATABASE_URL` **未设**时 `create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/matching.db")`（pytest tmp 隔离 SQLite + PRAGMA foreign_keys）；**设置**时强制 `postgresql+asyncpg://` 并创建一次性 schema `cp_test_<uuid>`。
- `backend/app/tests/test_jobs_api.py:22` `jobs_db`：固定 `sqlite+aiosqlite:///{tmp_path}/jobs.db`。
- `backend/app/tests/test_mcp_postgres_isolation.py:1-43`：PG 专项仅在 env 显式选择 PostgreSQL 时运行，否则 `pytest.skip`。
- `backend/app/tests/conftest.py`：autouse 关闭外部 AI（`ai_provider="mock"`、`ai_external_enabled=False`），不消耗真实模型。
- 出网核查：provider 测试全部 `httpx.MockTransport`（如 test_bailian_provider.py:29、test_deepseek_provider.py:173）；`test_mcp_stdio_integration.py` 仅绑定 `127.0.0.1` 临时端口且 `lifespan="off"`（app/main.py 的 lifespan 只在真实服务器启动时运行，ASGITransport 不触发）；无测试引用 `settings.database_url`（业务库默认串）。

## 命令与真实退出码（cwd=backend，子进程 `env -u CAREERPROOF_TEST_DATABASE_URL PYTHONIOENCODING=utf-8`）

| 命令 | 结果 | 原始输出 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -m pytest app/tests -q -p no:cacheprovider --basetemp=D:/jbcode/tmp/pytest-phase-sqlite-20261005` | **906 passed, 24 skipped, 6 warnings**，180.15s，EXIT=0 | pytest-sqlite-full.raw.out |
| `.venv/Scripts/python.exe -m ruff check app evals` | All checks passed!，EXIT=0 | ruff-check.raw.out |
| 4 个引用 PG env 的文件 `-q -rs`（仅枚举跳过） | 18 passed, 16 skipped，EXIT=0 | skip-reasons.raw.out |
| 全量 `-q -rs`（仅枚举跳过原因，选集同全量） | 906 passed, 24 skipped，EXIT=0 | skip-reasons-full.raw.out |

## 跳过归属（不冒充已验：24 个跳过全部为显式 PG 专项，未执行）

- "Requires an explicitly configured isolated PostgreSQL schema"：test_application_verification.py:717/755/932[3]、test_applications_api.py:395、test_knowledge_semantic_postgres.py:152/173、test_visual_postgres_concurrency.py:37[4]/135[4] —— 合计 16。
- "Requires explicit local PostgreSQL test database and real row locks"：test_mcp_postgres_isolation.py:147/224/290[4] —— 合计 6。
- 行锁类：test_evidence_growth.py:347、test_notifications.py:148 —— 合计 2。
- 16+6+2=24，与 pytest 全量计数一致；逐条行号以 skip-reasons-full.raw.out 原始输出为准。
- PG 专项阶段另由 Codex 安排；本阶段未连接 PG，未执行上述用例。

## 备注

- 6 个 warnings 为依赖弃用告警（如 swigvarlink 等），原始输出完整保留；未做任何修复（只读阶段）。
- 输出编码：以 `PYTHONIOENCODING=utf-8` 保证证据文件为 UTF-8；该变量仅影响 stdio 编码，不改变测试行为。
- 本目录外未写任何文件（除 pytest 临时目录 `D:/jbcode/tmp/pytest-phase-sqlite-20261005*`）。
