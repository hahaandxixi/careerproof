# OPS-01C 主匹配持久请求阶段签收

2026-10-08。签收范围为主匹配的规划、分析、修正及物理重试持久账目接入；共用日预留、跨午夜准入和依赖公告审计仍未完成。生产源码沿用15144e2，本轮只补独立风险测试，没有新增真实模型调用或业务库迁移。

## 独立生命周期证据

- `review-lifecycle-sqlite2.raw.out`：14通过，退出0；`review-lifecycle-pg.raw.out`：新增review与原durable_matching合计21通过，零跳过，退出0。PG使用随机自有cp_test schema，逐表namespace检查先于合成seed。
- 取消发生在可信收据提交之后：服务出口保留原CancelledError，正常费用结清；账目写入失败时保留received_unbooked，真实过期恢复器结束任务，账目恢复1/0且HTTP数不增加。断言设在execute_match_task边界，后台runner的响应不能代替取消传播证据。
- HTTP期间真实租约恢复：旧run费用保留一份，任务FAILED、run_token清空，没有报告复活。
- 报告已实际flush之后的SQLAlchemy before_commit注入失败：报告事务回滚，先前独立可信账目提交仍保留。这不是数据库断线或COMMIT确认丢失实验。
- 首次发送前简历/项目完成状态，以及固定resume/project/history选择遭改变：0HTTP、0账目、not_sent关闭，不保存报告。
- 两轮实际规划分别持久化planning_round_1/2，随后analysis；同run序号1/2/3、费用准确、可信全量标志为true。规划503未知与分析429/repair的既有独立用例继续验证部分可信480/155、整体usageKnown与usageBooked为false。
- HTTP期间owner或材料状态失效：可信费用保留，最终报告发布授权拒绝。此前3红灯、修复后4绿灯及受影响PG92/SQLite91+1PG跳过见kernel-checkpoint，不能拿ZCode修改前全量作为当前全量。

首次扩展SQLite为12通过/2失败，日志`review-lifecycle-sqlite.raw.out`保留：错误是把后台runner取消等同于HTTP端抛异常。调整观察位置后保留原异常字符串断言，并实际执行费用恢复断言；没有弱化生产取消处理。Ruff目标文件通过。

核验链的真实四窗口进程硬停及Codex独立复跑在OPS-01B签收中。此处的协程取消与事务故障不冒称新的主匹配进程硬停；预算实施卡仍要求两链预算接入后真实子进程四窗口验收。

下一步按共用日预算具体协议实现持久容量、未知占额、旧attempt接续与午夜准入，再进行当前依赖与权威公告审计。P2 stash、原业务投递快照、closure和远端Git保持不动。
