# 本地合成核验适配检查点

2026-10-10。目的：在升级后的独立 E2E 环境走真实企业核验、授权复查、持久收据及页面流程，不调用真实 DeepSeek。

- 新入口 `evals.e2e_verification:create_app --factory`，由 Start-E2E 的显式 `-SyntheticVerification` 开关选择。默认生产与原 E2E 入口不变。
- 工厂在覆盖任何核验函数前核对 run、loopback、精确 cp_e2e_<run> 库、专属存储、Mock 和外发关闭；业务库、远程库、错误目录、外发开启均拒绝。
- 仅核验模块的 provider/identity 采用 `e2e-mock`，普通主匹配继续 Mock。HTTP 永久绑定 httpx.MockTransport，使用合成 key、固定合成回答与合成用量。官方形状 URL 不产生实际网络请求，不能把该用量当真实厂商费用。
- 实际调用 provider 的 bounded JSON 方法并交给生产 validate_verification；不伪造引用或支持结论，不把本人贡献当已证明。测试封禁真实 AsyncHTTPTransport 后仍通过。
- 首次组合测试因系统 pytest 临时目录 WinError5 出现11项 setup error，原始日志 synthetic-verification-final.raw.out 保留。随后使用全新项目内独立 basetemp，29通过、零跳过；原始日志 synthetic-verification-isolated.raw.out。Ruff 与 PowerShell 语法通过。
- 该检查点尚不证明页面生成/复用/撤回/预算提示通过。需先保留当前进程日志与快照，按 RunId 自有进程身份停止并 SkipSeed/SkipBuild 重启，再实际操作页面。旧原投递快照、已发送回复及 P2 stash 不改。
- 后续实际启动已完成（synthetic-startup.raw.out）：原自有PID已不存在且8001/3001无监听，归档旧日志后清理该run失效manifest，再SkipSeed/SkipBuild恢复，夹具verify-only通过。工厂入口、Mock/外发false已在manifest确认，实际 /api/v1/health 与 /login 均200。误探测 /health 返回404，不能视为服务健康失败。
- 企业页面首验真实POST返回202，任务终态FAILED，独立只读PG查到 `budget_cutover_not_enabled`。新库预算闸门尚未经过管理员切换；未发生真实模型请求。原 enterprise-verification.raw.out 保留CDP等待超时，不把该超时当作后台拒绝原因；runner改用短分段观察并保存页面错误。
- 下一必须通过管理员审计流程启用本合成库预算，再验收成功生成/缓存/撤回，不能SQL改闸门或吞掉预算拒绝。当前服务仍运行，不能重复seed或仅因观察超时重启。
