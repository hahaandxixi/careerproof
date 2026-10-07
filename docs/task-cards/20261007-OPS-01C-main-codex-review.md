# 传智杯19 Codex只读审查：验收前必须核对

2026-10-07。首次依据正在编写的`backend/app/tests/test_durable_matching.py`，文件mtime22:38:28；这是进行中版本的审查，不代表ZCode终稿或测试已运行。Codex不修改19所有权文件，不同时运行数据库fixture。本文件为Codex所有，19证据目录仍由ZCode独占。

1. **unknown与usageBooked语义不能被测试倒逼改弱。** 当前已签收`AttemptService.summary`明确`usageBooked = usageKnown AND 所有可信attempt均booked`。有一个未可信的实际发送请求时，整体usageKnown/usageBooked都必须false，即使全部已知部分已经记账。首次测试中`expected_states`允许usage_unknown，但断言`summary["usageBooked"] is True`、metadata同样True，需改成整体语义；若确实想展示“已知部分已入账”，须独立命名字段而非重定义usageBooked。冻结的核验内核不能为满足错误断言而改动。
2. **完整规划链路必须实际发生。** 首次handler写“Planning (if reached)”并只要求`len(calls)>=3`，允许仅analysis(429→成功)+repair就通过，不能证明规划→分析→repair各自的物理请求均接入。需通过确实可补取的材料或授权历史fixture触发规划，明确断言planning实际发送的step/顺序/次数、503 unknown仍留存及该错误没有ledger；分析429的可信usage必须照实记入。另加多轮规划场景或明确独立测试，不能只从calls推导expected再和自身比。
3. **准确验证消费事实。** 首次ledger断言最后一个input_tokens>=0较弱；应按已知固定usage逐个核对seq的input/output/cache、partial总量，明确没有旧聚合行及不重复记账。known-only与混入unknown两个场景分别断言usageKnown/usageBooked，真实零usage与缺失usage不得混为一谈。
4. **隔离guard覆盖所有实际使用表。** 首次fixture虽create_all(checkfirst=False)已避免public旧表遮蔽，但逐表namespace断言只列7张表；注册、组织/岗位、材料上传还使用其他表。按创建/实际使用的表集合检查namespace，并先于任何seed/注册/上传；knowledge_chunks仍排除且不得调用其查询。失败finally清理只删除自身随机schema。

其余任务卡要求仍完整有效：解析/引用降级、取消/租约/报告保存失败费用独立结清；book失败0额外HTTP；owner/材料/固定snapshot新鲜授权0发送；旧run无报告复活；legacy兼容及旧账目hash；历史loader HTTP期间主session无借用事务的专属PG探针。一次happy-path+重试测试不能替代这些门槛。交棒时提供实际红灯/修复/受影响PG与SQLite输出、退出码、自审及停止写入声明，Codex随后独立复验。

当前UI工具连续人工输入保护，尚未确认将本审查消息发送给ZCode；不能把文件落盘当作对方已读取。恢复UI后只发送此文件路径与要点，不另起重复写入任务。后续以最终diff和新证据重新审核这些发现。
