# B-08：已发生模型用量在任务租约失效后仍幂等入账

1. 目标：仅修 `application_verification` 的已知用量丢账窗口；先写会失败的合成故障注入测试，再做最小实现。
2. 触发：provider 已返回有效 `usage`，随后 `finish_task` 因租约失效返回 False、撤回、取消或收尾 commit 失败；现有用量行会丢失。
3. 验收：可信用量在独立短事务中持久化，和任务结果/投递授权终态解耦；同一 `run_token + request_seq` 重试只写一行；撤回后绝不保存结论。
4. 事实判定：只接受响应中实际存在且 `prompt_tokens` 与 `completion_tokens` 均为非负整数的 usage；缺失、无效或未收到响应不写账单事实，不造估算行。保留现有前端展示语义，必要时明确标注 usage 未知。
5. 设计边界：迁移新增可空幂等列及部分唯一索引，旧行无损；验证任务每次 claim 的 `run_token` 和真实请求序号为键。provider 捕获后尽早落账；取消期间使用独立 session 和有界等待，异常不得伪装为已入账。
6. 预算口径：已入账的取消任务也计入真实 token；`reportCount` 按不同 task 数而非 usage 行数统计。注意模型调用前释放预算锁，已有在途请求仍可能并发超额，本卡只记录该局限，不宣称已解决。
7. 允许修改：相关 provider/verification/预算服务、`AiUsageLog` 模型、新迁移及定向测试；新建 `docs/evidence/20261004-B08-implementation/` 证据包。
8. 禁止修改：其他 AI 工作流、前端、正式 Bug/接力清单、B-11/B-16 文件、P2 stash；禁止真实 DeepSeek、真实简历、对外消息、Git 提交/推送。
9. 测试：有效/缺失 usage、租约 CAS 失败、收尾 commit 失败、重复记账、取消、撤回不落结论、预算 distinct；SQLite 与隔离 PostgreSQL 定向测试，适用的 Ruff 和后端全量。原始脱敏输出、退出码和 review-agent 自审入证据包。
10. 停止条件：若必须扩大到其他工作流或无法在有界取消窗口可靠提交用量，先交最小可运行补丁与失败测试，说明剩余风险，不放宽授权或幂等约束。
