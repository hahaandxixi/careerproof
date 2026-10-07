# 共用预算服务内核检查点（尚未接入模型调用链）

2026-10-08。Codex唯一写入`services/ai_budget.py`与`test_ai_shared_budget_service.py`。数据层承接66321f8。传智杯20尚未发送，不存在ZCode预算文件写入者。

## 已落地与证明范围

预算政策使用服务端配置快照；同owner/day先数据库唯一插入再排他锁，跨日升序锁；reserve将请求上界按日剩余与同task跨run报告剩余裁剪并保存持久hold。Capacity按held上界、settled可信实际、adjusted审计政策、released零占用统计，现代ledger不重复加总，旧attempt_id NULL账目按原created_at本地日计入。

服务支持严格旧0016 attempt接续：received_unbooked/booked重新校验usage_raw与全部计数，原发送日settled；未知按原日held；明确结束且未发送的not_sent释放，活未发送仍held；缺日期/身份/收据即拒绝，原attempt不改写。持久闸门缺失/禁用或任何未接续attempt都会拒绝reserve。闸门激活与旧聚合无收据的审计流程尚未实现，不能直接写enabled当作安全切换。

settle保留超过原上界的实际消费，迟到收据仍归原日，同报告新准入会被已超额容量拒绝。午夜transfer要求真实当前事务已经持有两日锁，并保持原批准上限；服务内核异常需要调用者原子关闭未发送请求。**目前未接入AttemptService/observer，因此没有wire上限、0额外HTTP或恢复全链路证明。**

实际命令：`pytest app/tests/test_ai_shared_budget_service.py -q --tb=short -p no:cacheprovider --basetemp=.tmp-budget-service-{sqlite3,pg2}`。SQLite最终13通过、1真实PG锁跳过；显式本机CAREERPROOF_TEST_DATABASE_URL的专属cp_test最终14通过、零跳过；原始budget-service-sqlite3.raw.out及budget-service-pg2.raw.out。6项是纯容量规则断言，其他为相应数据库fixture，不把14全部称作数据库集成用例。Ruff两个文件通过。

专属PG两个独立session同步进入最后一个报告槽竞态：只有一个300 grant，另一方daily_report_limit，数据库仅1份预留。此测试直接调用服务，不运行模型HTTP。另验证跨run剩额200、午夜旧日0/新日100与300、迟到实际1100/700仍原日且阻止后续报告消费、严格接续3/0、缺日期零接续。事务提交后日锁标记不可复用：标记绑定SQLAlchemy真实transaction对象，新事务transfer拒绝。

首次SQLite失败是测试把SimpleNamespace当字典，第二次是未处理SQLite的database_url=None，原始两次失败日志保留；未将fixture错误写成产品缺陷。第一次PG13通过属于加入事务身份修正前快照，最终以PG2的14通过为准。

## 下一具体实现

将本服务接入prepare/intent/receive/book/close/mark_unknown/reconcile，统一User/Task/业务授权→day→attempt→reservation→ledger；observer使用同一持久批准值设置实际请求max_tokens。发送/收据故障不重发，午夜失败原子关闭并归还确定未发送占額。完成旧聚合审计/闸门管理员激活、不可覆盖调整审计；不得只凭现有gate字段放行旧未知run。之后补两链真实四窗口硬停和独立故障复验，最后权威依赖公告审计与升级排序。业务库/closure闸门未切换，未安装、升级或部署。
