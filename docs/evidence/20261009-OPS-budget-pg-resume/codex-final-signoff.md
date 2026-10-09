# OPS-01 最终有界签收：持久账目、共用预算与硬停

2026-10-09。基线 c10dc1a；Docker Desktop由用户打开，引擎查询恢复后发现 backend-postgres-1 停止，Codex启动**现有容器**，只读 SELECT 1 成功。没有新建数据库/卷、迁移业务库或清理 socket。以后按用户要求用 computer-use 双击桌面 Docker 图标；规则已提交9fc1a04。

## 本轮修复

1. 生产入口PG首跑3通过1失败：匹配败方准入被拒且0 HTTP，但 workflow 在调用前计数令报告 requestCount=1。修正 analysis.py 的持久模式报告计数为数据库 intentCount，步骤载荷共用该值。发送意图表示可能发送，未持久收据仍unknown；未把意图数说成已确认HTTP或实际usage。原聚合兼容路径保持原语义。
2. 两链硬停首跑核验4通过、匹配4失败：子进程默认storage未继承父测试材料路径，真实解析提前失败。父配置传递绝对材料目录，worker在DB访问前验证属于本仓库 .tmp-*、同一state标记所在测试目录或其materials子目录。第二轮4失败因校验只允许materials子目录，而现有case实际用测试根目录；兼容两种真实夹具布局后8窗口通过。保留真实解析与全部硬停断言，未mock准入或把协程取消当硬停。

## 命令与原始证据

以下均在 backend，解释器 `.venv/Scripts/python.exe`，仅过程级 CAREERPROOF_TEST_DATABASE_URL 指向本地careerproof，fixture创建随机cp_test schema。没有修改.env。所有pytest加 `-p no:cacheprovider` 及独立项目basetemp，日志各自保留不覆盖。

| 检查 | 当前结果，退出码均0 | 日志 |
|---|---|---|
| test_ai_budget_production_race.py，-q -rs -s | 修复后4通过，零跳过；两个真实入口同owner双任务锁竞争、跨角色隔离/拒绝、单链契约 | production-race-fixed.raw.out |
| test_ai_shared_budget_service、attempt_integration、admin、workflows、fault_recovery、durable_matching、durable_matching_review、report_history、application_verification、durable_provider_hooks，-q -rs | 118通过，零跳过；当前预算/事务故障/授权/历史/规划修正重试受影响范围 | affected-pg-first.raw.out |
| test_attempt_hard_stop.py，-q -rs，审计plugin | 两链×四窗口8通过，零跳过 | hard-stop-final.raw.out；hard-stop-final/8份JSON |
| 同上 -k 'response_observed or receipt_committed'，新审计目录 | Codex另轮高风险复跑4通过、4有意未选，零跳过 | hard-stop-independent.raw.out；hard-stop-independent/4份JSON |
| test_ai_shared_budget_migration、hard_stop_worker_guards、budget_hard_stop_setup、ai_budget_production_race、real_matching，-q -rs | 最终49通过，零跳过；含固定SQLite DDL契约及专属PG案例，不能将全部49声称PG专用 | final-guards-migration-entry.raw.out |
| Ruff检查analysis及5个相关测试/worker/plugin文件 | All checks passed | ruff-complete.raw.out |

计数有重叠，不相加冒充全量后端；未改前端，不称新页面/真实模型/全站验收。各日志包含pytest模块与具体失败步骤。失败包括production-race-first、hard-stop-first、hard-stop-fixed、ruff-storage-final；匹配首轮child日志另存hard-stop-first-child-logs。原传智杯22 b轮两POST没有分类，仍保留未知原因；本轮PG与每次HTTP/attempt/收据一一对应守卫已验证，不以它证明原偶发原因已解决。

## 实际硬停证据

hard-stop-summary.json从12份原始审计JSON提取，每份核对真实PID/父PID/创建时间/nonce/schema/task/phase，再实际终止该worker，非取消协程。发送意图窗口0 HTTP仍保守unknown/held；收到响应但无持久收据1 HTTP仍unknown/held、无ledger；收据已持久1 HTTP恢复入账1/0；账目已提交1 HTTP恢复0/0。一律无新HTTP、task最终FAILED且run_token空，无业务报告/分析复活，固定投递快照摘要不变。

只读终检见database-readonly-final.json：12个审计记录的自有schema均已由fixture回收，未发现活动hard-stop worker。另有3个未确立本轮所有权的cp_test namespace，未作广泛清理；不声称数据库所有历史测试产物都已清空。

## 原目标完成审计

| 原要求 | 证明来源与实际范围 | 结论 |
|---|---|---|
| attempt/可信收据/幂等账目/旧聚合切换/撤回 | 核验37133e5内核/迁移/原4窗与独立复验；本轮118当前专项及预算后核验4窗 | 有界两链已证明 |
| 主匹配规划/分析/repair/物理retry，旧run不复活 | 9b9080b签收及本轮durable_matching/review、118专项、匹配4窗 | 已证明 |
| 共有日容量、真实wire grant、跨午夜/原日迟到结清、unknown不退额、6并发账目 | 本轮118中shared_budget_service/attempt_integration/admin/workflows；最终49迁移/守卫；生产并发4 | 已证明；同owner跨两角色真实入口不可达，分别同角色双任务及不同角色owner隔离，不削弱授权 |
| 当前提交故障与恢复0额外HTTP | 本轮118内fault_recovery，SQLite原aafee48与当前PG | 已证明；before/after commit注入不冒称实际网络断线 |
| 两链真实四窗口及Codex独立最高风险复验 | 8真实进程硬停+另轮4复跑，12原始JSON及汇总 | 已证明 |
| 无可信收据保留unknown | 两个未知窗口各链HTTP与held/ledger/recovery事实 | 已证明 |
| 完整迁移/往返/旧hash/有数据拒退 | 66321f8完整base..0017隔离证据；0016/0017源码未再改；最终49中的迁移复验 | 已证明隔离范围；业务库未升级 |
| 当前依赖版本与权威公告、升级排序 | 2565d80终审upgrade-ranking-20261009.md，244包版本成功查询、13命中、候选主要来源；本轮依赖清单/lock无改动 | 已交付；未安装/升级/部署 |
| 交接与有界后续 | 当前接力/任务清单更新，下一新ZCode任务23；80–100k只作经验阈值 | 已交付 |

因此本次OPS原目标的**核验与主匹配两链、隔离Mock+PG风险验收和依赖排序**完成。career_planning/visual_evidence/job_drafting仍属后续范围，不宣称全系统统一；真实模型调用/人工任意语义、业务库切换、依赖升级、推送/部署都未执行且另设有界任务。P2 stash继续暂停，用户空白行和历史未跟踪成果不覆盖。固定快照与未知费用边界作为后续不变量。
