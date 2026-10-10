# 核验预算页面状态矩阵的隔离控制

2026-10-10。仅修改显式启用的 `evals.e2e_verification` 工厂，不改变生产 provider 或已启动运行。固定控制文件为该 run 的 storage 内 `synthetic-verification-control.json`，不新增 HTTP 控制接口。

模式：known（缺省、合成100/80收据）、delay（0至15秒有界异步等待后返回known）、unknown（正常合成内容但不返回usage）、failure（503、最多一次物理尝试）。控制在每次物理请求开始时读取一次，不允许后续文件修改改变已经在途的响应。所有请求始终经过 httpx.MockTransport，地址仅为生产协议解析所用，不联网。

隔离环境验证先于覆写；非法模式/字段/布尔或越界延迟/损坏或过大JSON/链接路径拒绝，不回退到真实调用。缺文件保持此前known行为。坏文件在工厂初始化时拒绝，保持原产品identity/provider未改。

验证：target-receipts.raw.out共30通过，零跳过；包含原隔离守卫、生产生成方法、禁止真实transport及usage_present真/假断言。Ruff终检见ruff-receipts.raw.out。初次两条长行、追加测试一条长行已修；原终端输出和前序成功日志不冒称最新结果。测试未访问业务数据库、启动服务或使用真实模型。

这些证据仅证明隔离控制和收据解析，不证明页面矩阵完成。下一步新建独立run并先合法启用预算再播种，实际页面观察delay期间的held、unknown收据和failure；逐阶段用专属PG核对账目、原投递快照哈希、刷新/复用及严格390px布局。现有upgrade-budget-20261010运行不重seed、不改旧任务收据；控制不会热更新已加载的旧进程。
