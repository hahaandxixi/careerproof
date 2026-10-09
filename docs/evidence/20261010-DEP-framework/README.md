# FastAPI / Starlette 联合升级验收

2026-10-10，Codex执行（ZCode传智杯24首调用因五小时额度rate_limited且0输出，未重试，未同时写入）。基线f6ce263/559fdee。独立backend/.venv-dependency23；原venv和现有服务未升级。

## 变更及兼容

FastAPI0.116.1→0.143.0、Starlette0.47.3→1.3.1。Starlette同时钉生产dependencies与mcp extra，避免只装基础依赖时丢失审查过的版本。官方发布见fastapi-release.json/starlette-release.json；pip dry-run报告resolver-plan.json。

解析增加annotated-doc0.0.5与opentelemetry-api1.45.1；typing-inspection基线已满足，无额外升级。installed-diff.json逐项记录，未安装FastAPI standard extra或遥测SDK/exporter、未配置外部遥测目的地。使用项目原uvicorn启动方式。pip-check.raw.out清洁。

OpenAPI64路径的paths对象完全一致；components差异逐字段见openapi-differences.json。上传file Schema从format=binary改为contentMediaType=application/octet-stream；项目表单Schema正确反映现有camelCase别名materialRole/requestId，前端client.ts已经发送这两个字段。ValidationError Schema新增ctx/input描述，应用自定义错误仍只返回loc/msg/type；畸形含合成密码body的回归证明不回显。没有宣称Schema逐字相同。

## 实测命令及范围

均在backend目录以新venv执行，pytest使用-p no:cacheprovider与各自独立basetemp：

```text
python -m pytest app/tests/test_health.py app/tests/test_auth.py app/tests/test_portfolio_api.py app/tests/test_analysis_sse.py app/tests/test_mcp_sdk.py app/tests/test_mcp_tools.py -q
python -m pytest app/tests/test_framework_upgrade_contract.py app/tests/test_health.py app/tests/test_auth.py app/tests/test_portfolio_api.py app/tests/test_analysis_sse.py app/tests/test_mcp_sdk.py app/tests/test_mcp_tools.py app/tests/test_mcp_stdio_integration.py -q
python -m pytest -q
python -m pytest app/tests/test_dependency_environment_guard.py app/tests/test_framework_upgrade_contract.py app/tests/test_health.py -q
python -m pytest app/tests/test_e2e_fixture_safety.py -q
```

对应：旧框架目标68通过；升级目标72通过（含实际官方MCP stdio→合成本地HTTP→授权、撤销、审计链）；完整离线1090通过/46跳过，285.19秒；纯环境guard加入后目标8通过；既有E2E隔离guard18通过。全量收集发生在新增4个environment_guard之前，因此不能把1090说成新增guard也已全量覆盖，后者单独8项证明。跳过保持未验证，不用SQLite冒充PG。

新框架3项测试真实应用生命周期与中间件、CORS允许/拒绝、错误脱敏与requestId、sse-starlette3.0.3顺序两事件；合成SSE测试不是网页或持久任务取消验收。旧健康测试会启动业务恢复，本批通过monkeypatch隔离其_recover_once/stop_dispatched_tasks；新生命周期测试明确核对recover/stop各一次，不访问业务库。

专属PostgreSQL测试59通过/0跳过，pg-risk.raw.out。命令：

```text
python -m pytest app/tests/test_mcp_postgres_isolation.py app/tests/test_application_verification.py app/tests/test_durable_matching.py app/tests/test_ai_budget_production_race.py -q -p no:cacheprovider --basetemp=.tmp/dep-framework-pg-20261010
```

父进程只从现有配置取得loopback asyncpg URL，不打印连接凭据，先SELECT1；子进程仅设置CAREERPROOF_TEST_DATABASE_URL，夹具创建并销毁自身随机cp_test schema，namespace预检保留，不更改业务行/public数据。目标包含授权撤销、核验锁释放、持久收据和共用日最后槽真实生产入口整合。此59项不等于全量46个跳过项全部补齐，也不是升级后生产页面验收。

## 升级环境启动保护

Start-E2E.ps1增加-BackendVenv（仅backend下.venv或.venv-*，拒绝路径穿越及reparse目录）。evals.verify_dependency_environment在任何数据库连接/建库/迁移/服务启动前核对Python3.12及全部生产exact pin，启动manifest写入已核对runtime。原PID/创建时间/存储/固定8001/3001/强制mock/外发关闭约束保持。

实际pwsh -NoProfile -File scripts/Start-E2E.ps1 -RunId dep-preflight-20261010 -BackendVenv .venv-dependency23 -CheckOnly通过；使用仅供语法检查的合成E2E_DATABASE_URL，无建库或起服务。旧.venv选择在FastAPI版本核对时exit1拒绝，原文old-e2e-refusal.raw.out。两次都不是实际迁移/页面验收。

Ruff新测试/guard/健康测试通过。保留anyio BlockingPortal和httpx TestClient弃用警告，当前未移植httpx2，不视为运行失败或偷偷增加包。首次安装及每段原始输出保留；未推送/部署、未真实模型/邮件外发、P2 stash未动。

下一项：前端Next/sharp/source-map补丁及Next嵌套PostCSS独立修复，其他依赖处置；随后新环境真实迁移/合成页面链路和AI评测三维实现。整个目标尚未完成。
