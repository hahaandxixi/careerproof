# PRODUCT-01 Codex 首轮实现前/中审查

2026-10-05。HEAD f18c8ea；ZCode 免费 Flash 后端任务仍在运行，非交棒记录。

## 当前证据

- 实际落盘 test_growth_answer.py、test_growth_answer_migration.py、test_growth_answer_postgres.py，以及独立模型、严格请求 schema、服务初稿。
- ZCode 页面显示红例 9 失败、PG 3 跳过；这仅是执行方当时输出，Codex 尚未复跑，不作为通过证据。正式 PG 验收必须设置专项环境且零跳过。
- 初稿服务先本人所有权检查，PUT 使用父任务 User→growth 锁，expectedRevision 冲突返回 409；冻结基准读取 base_snapshot，目标读取 owner-authorized report。
- refs 列表路由协议已在任务卡定义并排入同一任务，当前不得认为已经实现。

## 已回传修正要求

- 第三方来源测试不能依赖 if reference_marked 条件跳过；需确定参考数据存在并实际断言 provenance=reference。
- 若测试第三次保存，刷新期望必须对应第三次保存回执。
- 补冻结基准/尚无草稿/跨岗位无原要求/其他学生与企业拒绝的 references 列表覆盖。
- 通知反馈已在同一 ZCode 任务队列界面确认，未另开写入者。

## 下一验收门

等待执行方终态交棒，审查最终服务/API/0015、原始输出和当前 hash；运行独立 test_private_answer_contract.py 与 PG 高风险并发。当前不批准前端开始、共享库迁移或服务重启，不提交半成品功能。

## 第二轮边界补验

- 完成状态并不等于可用目标报告。当前服务初稿仅按 analysis_task_id+COMPLETED 查目标，未对齐既有 growth 读取对固定 jobId/材料一致性的检查。
- Codex 已新增独立 test_completed_target_with_drifted_fixed_job_cannot_be_used_as_answer_source：完成真实合成分析并保存目标引用后，仅在临时 schema 修改分析固定岗位；原 growth 必须 409，草稿保留文字与版本、原引用记录但不可用，可选列表不释放错配目标、新保存拒绝。
- 测试尚未运行，待单写入者交棒；修复要求回传原 ZCode 任务，不并行改服务代码。
