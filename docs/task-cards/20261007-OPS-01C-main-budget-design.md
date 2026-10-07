# OPS-01C 主匹配与共用预算设计准备

2026-10-07。OPS-01B核验链已阶段签收37133e5；主匹配批准接口与文件范围见[主匹配实施卡](20261007-OPS-01C-main-implementation.md)。共用日预留/跨午夜仍为设计门槛，未实施。传智杯16/17/18已终态，本卡旧16所有权声明已失效；新的单写入者按当轮卡核对，不用准备卡代替完成。

## 当前源码证据

services/analysis.py:137的_daily_ai_budget用User FOR NO KEY UPDATE（SQLAlchemy的key_share=True、read=False）与已入账统计，会串行保护当前检查事务，但在事务释放后没有持久在途预留，不能阻止后续两任务同时进入HTTP；按AiUsageLog.created_at划日，硬停恢复后日期可能不同。execute_match_task在run_evidence_workflow后、终结报告事务才写聚合AiUsageLog；工作流自行get_ai_provider，调用规划/分析/定向修正及provider物理重试。task_lifecycle.finish_task按RUNNING+run_token CAS，旧run不能保存结果，此边界须保留。以上为本轮实际读码，未跑新的并发预算试验。

## 主匹配集成门槛

- 在工作流建立provider时注入由服务端task/claim/owner固化的durable observer工厂；planning/analysis/repair/每次HTTP retry均有独立物理attempt，阶段号用于查询，不复用成功次数。
- 服务端材料/岗位快照与授权新鲜复核、旧run不得发布报告、报告来源与评分守卫均保留。HTTP期间主session不得持续持事务/授权锁；进度回调不能无意开启事务并一直挂到下次HTTP结束。
- 新durable模式入账独立于workflow成功、fallback、报告保存和finish_task CAS。取消/租约失效/解析失败/规则降级仍结清可信消费；unknown不能塞成0的真实账目。报告中的显示usage与账目状态分开。
- 新模式停止原终结聚合写账，旧路径明确分流；单任务多attempt的可信消费按attempt唯一键记一次，原legacy账目不删除或重编号。不用报告内统计加账本行再重复计费。

## 两链共用日容量协议

1. 建user+Asia/Shanghai day唯一容量/准入记录，短事务用排他行锁和CAS，明确区分NO KEY UPDATE与KEY SHARE，不把参数名直接当SQL锁模式。首次物理发送前同时锁定日容量、稳定attempt，核对实际已知消费+尚未结清上界；所有核验和匹配入口用同一准入服务。未获准必须0HTTP。
2. 每个物理attempt预留sanitized messages保守input上界与max_tokens输出上界。report/task同一天的报告次数槽只占一次，不按重试增加次数；同任务多次规划/修正/重试的报告总上限同时计可信用量与未知预留，不能只看provider.combined_usage成功响应。
3. 可信收据持久、账目幂等提交和容量结清统一锁序：user授权（若需要）→按日期升序的day容量→attempt→ledger。恢复先只读取得归属，再按此锁序复读；不能先锁attempt再反向锁day造成死锁。所有网络在事务外。
4. 收据到达结算真实值、释放差额；超过保守预留的可信消费仍照实入账并标预算偏差、停止后续准入，不能为了保持预算数字拒记实际消费。重复恢复不能多退额、多扣账；received_unbooked不同时按实际和原上界双计。
5. not_sent且确定未发可以归还预留并留原因；in_flight/usage_unknown保留上界，不能按TTL直接归还或伪造已结清。关联run活跃时不得把慢请求抢为unknown。用户有权限的状态查询须可解释未知；人工调整预留要有操作者/原因/时间/前后额审计，不改变provider事实。先提供内部受控服务，不能暴露别人的业务正文。
6. 发送意图提交时固化当地日；跨午夜重新核对准入，把确定未发送的旧日预留转到新日，再提交新发送意图。明确本系统归属采用意图提交日，不谎称消除事务提交与物理网络之间的不可原子窗口或与上游账单日期精确一致。延迟收据按原固定日恢复，不按created_at恢复日重新消费。多日锁按日期升序。
7. 迁移/启用时旧账目纳入统计但不重写内容，新attempt与legacy聚合只能选择一条路径。不遗漏升级时活跃旧run的潜在消费；隔离试验明确切换/排空策略，不在业务库自动处理。不能因新表空就把用户已消费预算重置为0。

## 验收与后续责任

ZCode负责批准后的单写入者实现/原始回归/PG并发与四窗口硬停；Codex复核主链接入完整性、预算/事务/未知边界，独立最高风险并发及跨午夜探针。必须覆盖核验+匹配同时发送仅一个获准、重复预留/恢复、无效usage未知保留、规划/修正/HTTP重试都计入、午夜延迟收据归原日、未知人工审计、账目提交失败不额外HTTP、旧run入账不发布、legacy旧账目hash与多次迁移往返。

未知窗口继续unknown，不以一般异常测试替代真实进程硬停。阶段签收后才当前依赖版本/权威公告审计并确定升级次序；career_planning/visual_evidence/job_drafting未接入者独立列出，不称全站预算统一。保持Mock/专属PG，无真实外发、业务迁移、部署、安装或推送授权。

## 主链事务实测读码补充

update_task_progress实际内部commit，不能一概视为HTTP期间持锁。report_history.prepare_history_tool与返回read函数借用主session；每次历史MatchItem查询会开事务，应明确短会话释放。持久hook须在工作流规划/分析/修正各调用前设置，provider内部物理retry共用run序号。此段为现行源码核对，不是新增测试或实现通过。
