# OPS-01A Codex调查复核

2026-10-06。传智杯12（01a1105e-567f-7522-a125-6650470499ad）已实际终态交棒；本页由主会话写入。接收只读调查，不代表实施或故障验收通过。

- 已独立核对：_daily_ai_budget统计已账且采用User key_share；核验发送前commit释放事务。provider.request_seq在成功响应捕获后递增，不是物理外发编号；主链终结事务才保存聚合AiUsageLog。调查结论与当前代码一致。
- 首修次序：请求尝试持久状态/可信用量恢复协议，随后两链共用在途预留准入；不先声称统一全系统预算，因为career_planning/visual_evidence/job_drafting另有调用。
- 实现前还需明确：旧聚合账本与新逐尝试记录切换不能双计；旧run响应只修其请求账目不能恢复任务结论；unknown占额必须可查询/解释并保留人工处理审计，不能无记录无限冻结用户，也不能TTL直接抹掉可能消费。
- 发送意图持久化后与实际HTTP之间有不可消除窗口，应标可能发送；没有provider权威收据不能声称精确硬停对账。预留、usageKnown、usageBooked是不同事实。
- 调查报告与命令日志已落盘；真实硬停/DB恢复/PG并发均仅设计。无实施授权下发，不动当前PRODUCT-01文件和数据库。

下一门：先完成PRODUCT-01私人草稿验收；以本报告及原任务卡定有界OPS状态机/迁移卡，批准后才实现。当前Docker恢复仍影响PG实验。

## 2026-10-07 锁语义勘误（实际编译验证）

先前“User key_share”用词只引用了SQLAlchemy参数名，不能理解为FOR KEY SHARE。当前安装库实际把with_for_update(key_share=True)、read=False编译为FOR NO KEY UPDATE：[只读编译原始结果](../20261007-OPS-01B-codex/lock-clause-compile.raw.json)。当前检查事务确实串行用户行；预算缺口来自检查事务释放后没有持久在途预留，原修复方向不变。

[PostgreSQL官方行锁文档](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS)说明NO KEY UPDATE与KEY SHARE兼容。撤回持Application锁后可能插入企业通知而取User外键KEY SHARE；新发送前若先取User FOR UPDATE再等Application，可能形成反向等待。应保留与FK KEY SHARE兼容的User短锁，任务身份锁也避免不必要FOR UPDATE，具体并发路径仍须PG实测，本文不代替测试。
