# 夹具隔离核对（最小确认）
- conftest.py:6-10 autouse `disable_external_ai_for_tests`：强制 settings.ai_provider="mock"、ai_external_enabled=False（禁真实模型/外部AI）。
- test_real_matching.py:53,58-59,81,109 `matching_db`：仅当 CAREERPROOF_TEST_DATABASE_URL 显式配置时用 PG；schema 名 = f"cp_test_{uuid4().hex}" 且断言 `cp_test_[0-9a-f]{32}`；CREATE SCHEMA 于 setup，DROP SCHEMA ... CASCADE 于 teardown。
- test_mcp_postgres_isolation.py:43 非 PG 则 skip（"Requires explicit local PostgreSQL test database"）。
- 结论：夹具满足任务卡要求（Mock 强制 + 自有随机 cp_test_* schema，不写 public/cp_e2e_closure-20261005）。
