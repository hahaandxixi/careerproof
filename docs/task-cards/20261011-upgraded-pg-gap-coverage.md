# 传智杯29：补齐升级环境剩余PG集成证据

2026-10-11。实际Git根D:\jbcode\web ai\jianli，main。Weekend Build免费Flash/最高，不用个人计划。28唯一写新离线runner/test；本任务唯一写docs/evidence/20261011-DEP-pg-gap-coverage/及自己的backend/.tmp测试临时目录/辅助脚本。生产源码、任何测试文件、正式文档只读；如确有失败先保留证据并交棒，不擅自修业务逻辑。

## 为什么要跑

升级工具链全量1094通过/46跳过。框架/工具链PG专项已覆盖其中18项；下列9模块的28项原跳过仍无本轮升级后证据。不能把79 PG专项当全部46已覆盖，也不再重复其18项。补全这9模块在新解释器下的受影响集成验证，特别是补证/通知/投递/跨进程锁释放。

目标文件（全模块运行，普通用例作为这次PG环境受影响回归）：test_applications_api.py、test_attempt_hard_stop.py、test_durable_attempt_service.py、test_evidence_growth.py、test_growth_answer_postgres.py、test_growth_target_postgres.py、test_knowledge_semantic_postgres.py、test_notifications.py、test_visual_postgres_concurrency.py。原跳过数分别1/8/2/1/3/2/2/1/8=28；逐个节点核对实际运行，不因普通用例数量大掩盖跳过。

## 安全与所有权

- 先核对HEAD/目标文件hash、读取上述fixture中cp_test schema创建/预检/清理、app/tests/conftest.py外发关闭保护；不得改.env/业务库/public、cp_e2e_question-chain-20261010或任何原run；不迁移业务库。已有Docker原postgres容器已启动，仅SELECT1连通检查，禁止容器/服务启停或安装。
- 从app.core.config.settings读取现有loopback PostgreSQL URL，在父进程捕获并传给子进程CAREERPROOF_TEST_DATABASE_URL；不打印或在证据写URL/密码/临时hardstop config，不把临时目录加入Git。每个fixture必须只创建/销毁自身随机cp_test_* schema；先确认引用表namespace，不能仅凭DB名猜隔离。
- 使用backend/.venv-dependency23/Scripts/python.exe，目标依赖pin运行时验证；每次pytest独立--basetemp=backend/.tmp/dep-pg-gaps-20261011-<suffix>、-p no:cacheprovider -q -ra。可先收集目标清单然后一次运行9模块，失败原文单独保留。真实硬停只杀测试自身nonce/创建时间核对的子PID；MockTransport/合成provider无真实外部模型/邮件。
- 本任务是唯一DB测试执行者；28离线测试不触DB，Codex期间只读审查，不同时跑PG或改夹具。

## 交付

README含精确命令、升级runtime、总通过/失败/跳过数、28原跳过节点及各自结果、隔离/硬停范围与未验证项。完整stdout/stderr只入证据目录，先检查无密钥/连接凭据。manifest记录HEAD、目标/fixture/runtime源hash、自审；报告限一屏。不重复已过全量、不要改断言或跳过策略凑绿灯。

禁止源码/测试修复、Git暂存提交推送、删除历史/应用P2、联网/模型/安装、修改E2E数据。完成交棒后Codex独立最高风险PG复验与本地提交。

## 首轮失败后的路径兼容补验

首轮60节点实测56通过/4 matching硬停失败；worker的validate_config在任何HTTP前拒绝`.tmp/dep-...`，它严格要求backend下`.tmp-*`首段且storage仅为本节点test_root或materials子目录。这是本卡basetemp约定与既有guard不一致，不改guard或业务源码。

补验只重跑test_attempt_hard_stop.py的matching四节点，使用新的自有backend/.tmp-dep-pg-gaps-*目录（如--basetemp=.tmp-dep-pg-gaps-20261011-matching-rerun）；root已批准这个仓库内兼容路径例外。仍须schema/表namespace/nonce/PID防护、外发关闭不变，不改原标签/断言、不覆盖首轮56/4日志，逐节点确认真实四阶段挂起/硬停/数据库恢复，而非只证明child启动。
