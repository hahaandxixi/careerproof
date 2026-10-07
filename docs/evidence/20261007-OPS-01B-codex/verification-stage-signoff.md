# OPS-01B 核验链阶段签收

2026-10-07。只签收持久请求核验链；完整OPS目标仍在进行，主匹配/共用日预留/跨午夜/依赖审计未完成。

- 实现与旧回归：d4ac845；独立核验/服务PG62零跳过、SQLite57通过5PG跳过。provider/parser受影响74通过c8286ab；模型迁移独立PG17通过3be0247。详见 kernel-review.md，保留所有失败和root测试夹具隔离缺陷的精确恢复证据，不追改为“从未发生”。
- 对协议逐项补验：service-contract-pg.raw.out 12通过。实际发送意图commit失败0HTTP并关闭not_sent；账目commit失败原子回滚仍received_unbooked，之后恢复1/0且HTTP仍1；6并发入账仅1事实、3并发prepare序号1/2/3；慢活claim的in_flight不被恢复器抢判unknown；迟到可信收据可结清旧run而不写业务结果；非法/篡改收据不得入账。
- ZCode18真实核验入口独立child四窗口首验4通过，两个失败日志分别保留。Codex源代码审查后完整独立复跑4通过/零跳过，hard-stop-replay.raw.out。没有把协程取消替代进程硬停。
- Codex只读audit插件不改变测试断言、恢复实现或child代码；hard-stop-replay/*.json保存每窗实际PID/父PID/OS创建时间/nonce/schema/task/attempt、硬停退出码1和两次恢复前后数据库事实。无可信收据的两窗是unknown、无账目；可信收据窗恢复1/0，已入账窗0/0；每窗HTTP计数保持0或1、任务FAILED/run_token=None、无业务analysis。原report_snapshot hash由不变的测试断言校验。
- 运行后只读CIM查询没有ops_hard_stop_worker.py进程；本轮未停止服务或任何非自有进程。硬停夹具只建/删自有cp_test schema，child数据读取前逐表验证namespace。原P2 stash与closure仍未改动。
- 完整真实Alembic env.py验证：verify_full_chain.py复用已审查保护helper，先建自有空版本表防止public版本表被解析；实际base执行0001..0016，再0016→0015→0016。合成旧账目全部原列规范化hash、旧合成report/application/growth行hash一致，full-chain.raw.out；自有schema清理通过。未升级业务库/closure。

后续先批准主匹配所有物理步骤/重试接入，禁用新模式旧聚合账目，再共用预算预留与跨午夜准入。禁止从本阶段通过推导真实DeepSeek调用、部署或全站统一预算已完成。
