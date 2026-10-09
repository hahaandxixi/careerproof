# OPS原目标逐项审计（早期检查点）

本页保留早期未完成现场；现行完成审计见[最终签收](../20261009-OPS-budget-pg-resume/codex-final-signoff.md)。当前PG/真实硬停门槛已兑现，不再按本页旧Docker阻碍安排任务。

2026-10-09，生产源码基线f14af62，文档基线2565d80；后续仅测试准备修复。按20261006-OPS-01B-durable-attempts及预算独立复验卡核对，不重定义目标。

| 原要求/门槛 | 证据与范围 | 当前结论 |
|---|---|---|
| 持久attempt/可信收据/幂等账目/旧聚合切换/撤回 | verification-stage-signoff.md，37133e5；kernel风险PG62、合同12、迁移旧hash、核验真实4窗首验+独立4窗 | 核验阶段已证明；预算后仍需复验 |
| 主匹配规划/分析/修正/重试，旧run不复活 | main-stage-signoff.md，9b9080b，生产15144e2；独立PG21/受影响92 | 主匹配阶段已证明；预算前证据 |
| 共用日预留/未知上界/发送日及午夜准入/管理员审计 | 66321f8/c270e57/14e19b9/f14af62；service PG14是此前范围；当前两链SQLite142+6跳过、分项17+1跳过 | 实现存在，当前PG和整合门槛未证明 |
| 两条实际生产入口同owner最后槽并发 | 服务层test_pg_cross_chain_last_slot_real_concurrent_sessions仅直接reserve；生产入口测试目前各自覆盖闸门及wire grant | 仍需生产链整合反例，不用服务层冒充两链完整验收 |
| prepare/intent/receipt/book提交失败、恢复不重发 | aafee48，codex-review.md目标8/受影响36+2PG跳过 | SQLite已证明；不是asyncpg断线或PG通过 |
| 两链真实子进程四窗口及独立最高风险复验 | test_attempt_hard_stop两链8项仅收集；hard-stop-setup-review准备13通过 | PG实际8窗口及独立复验缺失 |
| 没有可信收据保留unknown | 已签收内核/两链测试守卫及预算held断言 | 当前硬停后的预算事实仍需PG证明 |
| 当前依赖版本/权威公告/升级排序 | upgrade-ranking-20261009.md；244当前包版本0查询失败、13命中、原始152公告与候选来源；21已交棒 | 有界核对与排序交付；不等于安装或安全保证 |
| 接力/下一有界范围/编号/上下文 | 当前接力+任务清单+精确证据索引；下一编号22；80–100k为经验而非实时测量 | 接力规则存在；本目标仍保留 |

Docker当前故障为dockerInference系统不可访问，最新重启记录docker-recheck-20261009-1755.md；原CLI96044持续等待非健康证明。恢复前不做public/业务库操作、不安装替代环境、不工厂重置。还有可准备的生产链并发反例；因此本次不宣称完成，也不把目标缩为依赖文档。

## 角色可达性复核（传智杯22委派后）

独立读取application_verification.py:250/375及analysis.py:145：企业核验created_by为企业请求者，发送授权要求ENTERPRISE；匹配发送授权要求STUDENT。User单role，使此前“同User跨这两个生产入口竞争”无法合法构造。此为原测试设计前提错误，不能修改授权/伪造owner迎合测试。当前证据计划是：两种实际生产链各自同owner不同任务竞争最后槽，另证不同owner跨角色预算隔离与拒绝错误角色；共享内核跨chain同ownerPG竞争单独证明。各层覆盖分别登记，原目标共有日预算与午夜准入范围不变。传智杯22已收到角色修正并重新读取更新任务卡；尚未交棒或实际PG执行。
