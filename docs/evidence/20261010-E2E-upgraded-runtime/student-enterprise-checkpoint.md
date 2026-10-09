# 升级后学生与企业页面检查点

2026-10-10，本轮实际运行 upgrade-20261010，独立库、升级后的 Python/Next 环境；Mock，外发关闭。

- 企业 reply-failure 场景终态 exit=0：桌面 A 与390px B 各一次未送达请求、一次已送达但响应丢失。失败草稿可编辑、清空、重填；刷新按服务器事实显示，已送达不能重复发送。原始证据 enterprise-reply.raw.out 与新企业 evidence 目录。
- 学生 variant-materials 终态 exit=0：保存新版材料、生成新报告、逐项对比；变化背景仅材料版本变化，新增引用指向新报告。原始证据 student-materials.raw.out。
- variant-job、variant-both 均终态 exit=0：前者只显示目标岗位/要求变化；后者显示材料+目标岗位/要求变化，三个条目均有解释。跨岗位保留原企业问题/缺口/引用关联原岗位的提示，刷新后材料和目标仍与保存值一致。原始证据 student-job.raw.out、student-both.raw.out。
- viewport390、enterprise-recheck 均终态 exit=0：补证列表、任务、新报告没有横向溢出且标题不被导航遮挡；企业重新打开三份投递后原固定快照 hash 全部不变，原岗位A/B与要求保持一致。原始证据 student-390.raw.out、student-snapshot-recheck.raw.out。
- chain-reply 首轮失败保留 student-chain.raw.out。初始合成夹具没有企业回复，测试却在创建任务时要求该上下文；不得算通过。
- 企业普通回复补齐后复验仍缺上下文，保留 student-chain-after-reply.raw.out。服务 reply_context_for_requirement 只提取明确关联 requirementId 且含对应要求标题的人工回复块。reply-failure 使用通用正文，没有关联要求；因此该夹具仍不足以证明学生的“企业问题与新报告核对”路径，尚无页面产品缺陷结论。
- runner 增加异步上下文等待及缺失即停止，防止前置条件缺失时继续创建/分析任务，保留失败证据。已有合成任务和报告不删除、不改绑定、不修改已发送回复。
- runner 原投递复核改成读取本轮开页面前状态，只允许 submitted→viewed，已 viewed/replied 必须保持；所有原 ID 必须在、原凭据中的固定快照 hash 必须一致，不接受陌生记录。移除旧历史场景硬编码 replied/replied/viewed 的前提。目录参数与既有保护测试合计30通过、零跳过。

后续：通过新合成投递的正常页面发送具名、明确关联要求的回复，再走学生带问题补证路径。先完成只换岗位/两者都换/390px与原快照哈希复验；核验建议成功路径需独立合成 MockTransport 适配。真实模型、预算页面、AI三维评测仍未完成，不将此检查点当作全目标签收。
