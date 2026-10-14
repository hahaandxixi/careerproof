# 传智杯49：可复现CI与PostgreSQL必跑门禁

2026-10-14 Codex本地复核完成：门禁函数/参数误放行与两库vector初始化已修，独立PG87+8及真实JUnit门禁通过；20门禁/30工具、前端262/类型通过。来源与限制见[复核记录](../evidence/20261014-ci49-review/summary.json)。远端Actions与干净安装构建尚未验证，旧禁止真实DB的委派范围仅适用于ZCode原实现阶段，不代表Codex本次专属容器未执行。

基线 main/f781a5b；实际 Git 根 D:\jbcode\web ai\jianli。对应G3关键边界/G4复现/G5问题等级及整改P0-4.1/4.3。唯一实现写入者ZCode，Codex做只读协议复核与独立干净快照验收。

## 范围

唯一可写 `.github/workflows/ci.yml`、`backend/scripts/check_ci_junit.py`、`backend/app/tests/test_ci_junit_gate.py`、`jianli/package.json`/`package-lock.json`、证据 `docs/evidence/20261013-z49-ci/` 和临时 `backend/.tmp/z49-ci/`。正式文档Codex负责。不要修改业务源码、测试夹具、旧guard/launcher/P2、客户端记忆或配置。无需读/写全量历史文档。

## 协议

1. 三独立job：backend-unit（升级Python3.12，pip install -e '.[dev,mcp]'，版本核验，Ruff，全量SQLite测试）；backend-postgres（独立服务PG17+pgvector，专属数据库cp_ci，只运行下面必跑文件并写JUnit，严禁业务库）；frontend（Node22.23.1，npm ci→npm test→typecheck→build，顺序执行）。APP_ENV=test，DEBUG=false，AI_PROVIDER=mock，AI_EXTERNAL_ENABLED=false；无真实Key，禁止外部模型。unit unset CAREERPROOF_TEST_DATABASE_URL，PG显式postgresql+asyncpg://ci:ci@127.0.0.1:5432/cp_ci。使用合成CI凭据，不能读取本机.env。
2. strict PG文件：test_ai_budget_production_race、test_durable_matching、test_attempt_hard_stop、test_visual_postgres_concurrency、test_mcp_postgres_isolation、test_real_matching、test_durable_attempt_service、test_ai_request_attempt_migration、test_knowledge_semantic_postgres、test_ai_shared_budget_service、test_ai_shared_budget_migration、test_application_reconsent_migration。JUnit门要求每个module至少有用例、没有failure/error/skipped，且test_attempt_hard_stop两链四窗口8例全部实际通过；空XML/缺文件/漏窗口/跳过/格式错误均非0退出。不能仅看pytest exit=0。先为门禁写反例测试再实现。
3. 全量SQLite允许明确的PG/本地ONNX权重缺失skip，保留JUnit并注明范围，不伪装PG已跑或真实语义已验收。PG strict是上面的必跑集合，不因ONNX权重未知而排除这些PG文件。
4. 补声明sucrase==3.35.1为前端devDependency（现有tsx渲染测试直接依赖但未声明）。允许仅用 npm install --package-lock-only --ignore-scripts --no-audit --no-fund 更新锁；不更新其他包版本，不重写覆盖率/测试阈值、不改既有test命令或删除失败测试。检查锁无无关升级，不安装根node_modules。
5. 工作流 pull_request / push main / workflow_dispatch，contents:read、checkout persist-credentials:false，固定超时与并发取消旧CI；不能写仓库、部署或自动提交。失败时只上传各job的JUnit/测试日志，禁止上传.tmp/源码材料/.env/storage。upload if:always，保留7天。

## 已核实官方入口（2026-10-13，agent-reach/gh只读）

使用官方v7提交SHA固定（不要擅自解析新tag）：checkout `3d3c42e5aac5ba805825da76410c181273ba90b1`；setup-node `949feb2413d6458794dcd2491c4babbbce0c15c1`；setup-python `5fda3b95a4ea91299a34e894583c3862153e4b97`；upload-artifact `cf430e030ddbb5b0abf93d22962f4752f3646cd9`。来源官方actions/{name}/README与git/ref/tags/v7。PG镜像本机已有 `pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f`，保持PG17。

## 验证和停止

纯门禁红/绿测试、Ruff、YAML结构自审、package/lock差异与源码hash、原始日志（各失败分档）。禁止实际创建DB/启动容器或服务/真实硬停；这些由Codex独立执行。禁止Git提交/推送/远端分支保护设置、真实模型和外发私有数据。交棒限一屏，明确“本地门禁实现”不等于“远端Actions已成功/已强制合并保护”。完成有界任务后停止，不自行继续其他整改。不得修改客户端记忆/配置。
