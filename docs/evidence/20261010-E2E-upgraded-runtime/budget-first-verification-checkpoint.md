# 预算先审计后的企业核验页面检查点

2026-10-10。生产外发保持关闭；所有回答、usage 与HTTP transport都是显式合成，不能算真实模型质量或费用证据。

1. 旧 upgrade-20261010 预算激活被真实审计拒绝（budget-activation.raw.out）：既有带同意旧分析没有完整物理账目，保持关闭；事务回滚，不修改旧任务或闸门。其库、材料、三份原快照均保留。
2. 新 activate_e2e_budget 只允许严格本地合成run库/存储/Mock环境，用随机不可复用密码创建独立合成管理员，由生产 SharedBudgetService.activate 完成库存审计与切换；不直接改 enabled。业务库连接前拒绝测试通过；适配目标12通过，Ruff/PS语法通过。
3. 新运行 upgrade-budget-20261010 在迁移后、任何seed任务前激活空库存，再seed三份新合成投递。升级venv与frontend stage、0017、MockTransport入口；budget-first-startup.raw.out 保存激活actor/digest与启动证据。旧run自有服务停止，库不动。
4. 企业 verification 页面终态exit0：生成、复用、重新打开后已保存建议可读。独立只读PG verification-ledger.raw.out：一个COMPLETED任务、一个e2e-mock booked attempt（合成输入100/输出80）、一条settled预留，不重复入账。
5. download-withdraw 实际下载hash通过，学生撤回A，企业看不到A，B仍授权可下载。旧通知探针blocked：脚本定位按钮但没有发真实点击，首失败日志保留；已补点击，独立withdraw-verify继续验证，不能把blocked算通过。
6. both-run-snapshot-check.json 独立只读核对两套库，原各三份固定投递快照hash与凭据基线一致。状态变化与固定快照不变是不同断言。

当前独立withdraw-verify终态须看原始日志；服务属于upgrade-budget-20261010。下一仍有预算known/held/unknown/错误页面完整矩阵、具名关联企业问题的学生闭环、390px核验与AI三维/holdout/P2决策。不得把本检查点当作完整目标签收。

最终独立withdraw-verify通过（enterprise-budget-revocation-timestamp.raw.out）：旧A锚点不可用、旧通知不可用、其他两条打开锚点正确、无A报告泄漏。前次blocked因探针要求旧通知至少早60秒，新夹具投递到撤回不足一分钟；改成严格早于撤回且保留一秒显示精度保护，撤回事件取两秒内最近时间。恶意未来时间/同秒舍入/未知时间与40秒旧事件回归通过，运行器保护合计31通过。原两次失败保留。
