# 预算实际显示检查点

2026-10-10，产品修复提交d290aec；验收仍为隔离upgrade-budget-20261010、0017、升级解释器/前端stage、合成MockTransport、真实外发关闭。未重seed、未恢复已撤回A。

产品核验接口在每次授权读取得到当前owner日账目，复用保存任务也返回新账目；页面单列已知Tokens、保守预留、未知收据，避免把缺失收据写成零用量。后端PG42零跳过、SQLite37/5PG跳过、前端193及类型检查通过，原始日志在本目录budget-display-*。

自有PID/创建时间/命令匹配后停止原run，保留数据库/storage。顺序生产构建与实际启动通过；Next生成的next-env/tsconfig原字节恢复。见budget-ui-build-start.raw.out。

实际页面：B核验生成、复用、刷新通过；已知输入200/输出160、保守预留0/0、未知收据0。首次命令因证据目录大写被拒绝，无页面操作。第二次仅设Chrome窗口宽度，截图揭示其最小窗口限制，不能作为严格390px通过；第三次显式Emulation视口并断言innerWidth=scrollWidth=390，通过。两轮记录均保留，正式窄屏证据为[第三轮结果](../20261010-e2e-budget-known/budget-verification-2026-10-10T02-15-16-184Z/results.json)。

Codex独立只读SQL核对：2个booked物理attempt、2个各恰好一次settled预留、输入合计200/输出160，与页面一致；原A/A2/B三个投递snapshotSha256均不变。证据budget-known-independent.json；后续复用没有新增物理请求。

尚未完成：实际预留中/unknown/失败矩阵、关联企业问题正向补证、ZCode25评测与独立holdout。不能以本次known状态签收整个预算闭环或真实模型语义。
