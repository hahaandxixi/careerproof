# 当前核心路径修复与CI复现

基线`ba0c970ba39e3823c2c4bcf4ca58fdba4c587e0a`，真实Git根为`D:/jbcode/web ai/jianli`。原有多批源码、页面、文档及未跟踪成果保留，不把整个脏工作树当验收版。本批接受路径及逐字节SHA见`accepted-source.json`；副本为`backend/.tmp/core-acceptance-20261022/source`。PrivateAnswerDraft既有display-path改动及环境模板既有上下文说明未混入本批接受文件。`private-answer-workflow.ts`的另一处字节差异仅为行尾，接受源码以清单及Git规范化内容为准。

产品源码已分两批本地提交：`9f7b398`（预算、冻结输入和CI测试边界）、`7a76dd9`（兼容向量检索、私人草稿、材料配额及进程/文件生命周期）。36份接受文件的Git规范化内容均与验收副本一致，变更路径集合也完全相同；不是在整个脏工作树上通过后整体暂存。没有推送。

后续`ec1e5e5`仅收紧视觉队列超时的测试边界，总接受路径为37。真实50ms Timeout必须在零容量队列等待期间到期；保留provider零调用、失败任务、零用量及原图不变断言。删去生产timeout或移到队列之后的独立副本都被测试拒绝，不用整个HTTP的1秒耗时冒充模型预算。原整套1失败/1576通过/88跳过保留为`before-visual-watchdog-*`；无法从旧ASGI流堆栈认定具体慢阶段，不据此修改视觉业务逻辑。

## 实际修复

| 问题 | 原因与结果 |
| --- | --- |
| 默认AI请求在HTTP前失败 | 完整wire字节加1024余量已超12000；去重重复提示但保留完整证据规则，并按固定完整项目把默认校准为40000。最小有效请求16122→14520，完整五项项目39348→37746。两者实际到达Mock HTTP；仍受累计、逐次、规划预留、修正、重试和未知用量守卫约束。每日实际输入200000、输出4000等未提高。 |
| PG分页fixture仅单独运行可见 | 按CI多模块顺序复现8个setup错误；显式导出原matching_db，保持原随机schema隔离与清理，原顺序8通过。 |
| 执行器冻结输入漂移 | 旧授权包不再对应当前源码，保留拒绝旧包的回归；新增独立offlineOnly测试包，原材料/历史包/claim不改。另修正将单次20k错误当作整报告累计20k：逐次完整wire仍≤20k，累计仍受生产上限约束，硬停不被fallback吞掉。 |
| 向量空间混排 | 完整统计本人索引引擎，先在同一权限CTE限定引擎再计算距离；不抽样最新50条，不猜测无标签向量，不跨不兼容引擎降级。真正不同合成向量空间、旧索引/模型不可用/归档/不同owner回归通过。 |
| 离窗丢私人编辑 | 子组件清空之外，父组件也会卸载；现同身份/任务内存暂存、隐藏时作废在途回执、返回重验已保存版本。切换身份/任务仍销毁，不加浏览器持久缓存、自动保存或企业发送。 |
| 解压残留与上传准入 | 失败/超时/取消/失租/事务失败后先等待worker退出，仅回收本次未引用目录。成功或不确定COMMIT后已有DB引用的原件保留。新增按账号行锁的512MiB原件/解压/预留及4个pending/running名额；跨项目、简历和重试共用，幂等重放不重复预留。无需迁移。 |
| 归档与上传实际死锁 | 独立PG复现Project锁与User外键检查形成锁环；账号准入改为FOR NO KEY UPDATE，仍排斥另一准入、允许审计FK KEY SHARE。新增真实归档/审计/上传交错回归；原8项并发配额约束保持通过。 |
| Windows启动器退出不等于解析进程退出 | 保留真实worker的PID、创建时间和native HANDLE，父进程确认身份后才允许解析；取消/超时先等待实际进程退出。真实子进程反例与最终取消/超时证据保留。另以确定性反例修复重复取消打断teardown：整个退出流程在独立受保护任务中完成，仍透传第一次取消，不伪装成功。 |
| 前端整体回归的两个加载错误 | 既有TaskView新增MaterialContentNotice后，SSR测试加载器漏了真实组件导入。补加载真实组件，不改业务或弱化状态断言；382项完整前端回归通过。 |

## 验证与版本范围

历史GitHub run`39639164011`确属`7a19e6b`，元数据见`historical-ci.json`；不将其当当前结果。当前基线重新运行：1500通过、43失败、75跳过，其中31为预算路径，12为旧源码冻结包。失败输出及XML保留。首次沙箱异步测试无进展后中断，使用同样离线命令经审批运行；不改ACL。复跑期间发现marker-only崩溃残留枚举遗漏，停止未完成复跑并保留`unit-before-marker-fix-interrupted.raw.out`，补回收及回归后重跑。

首轮资源探针还包含探针构造/配置错误，不当作生产红例；有效的资源红例另存`resources-red2.raw.out`。首轮Settings错误输出的未脱敏副本保留在本轮私人.tmp，公开`resources-red.raw.out`明确标注JWT及数据库userinfo脱敏，不能当作逐字节原始日志；其余原始失败和成功输出按各次范围保留。

随后整体复跑的日志配置顺序污染已用精确顺序反例修复，仅改测试边界，仍保留预算异常外抛及安全日志断言（`unit-before-order-worker-fixes.*`、`frozen-packet/REPORT.md`）。重复取消修复前的一轮为1568通过、1失败、88跳过；失败是推荐测试准备材料时解析子进程异常退出，并非推荐排序断言。原始记录为`unit-before-repeat-cancel.*`；独立目标及带stderr诊断复现结果另行留存，不把后来通过说成已经解释了该次退出。

之后实际12次API诊断复现一次子进程读取私有worker.ack时PermissionError（11通过/1失败）；原全量单次stderr无法恢复，不补写成已捕获其堆栈。新增私有握手读函数只将PermissionError/FileNotFoundError视为暂不可读，父子双方在原deadline内重读；损坏JSON、非对象、nonce/身份不符仍拒绝，不改ACL或延长启动时限。永久不可读同样必须失败。修复后同一12次诊断全部通过，36个实际worker退出码0、stderr空，三份运行时SHA与最终清单一致（`ci-order/README.md`）。修复前另一轮完整SQLite1570通过/88跳过，但PG140通过/1失败，门禁确实拒绝；分别保留`before-private-read-*`，不把SQLite通过当作整套CI通过。

| 检查 | 结果与证据 |
| --- | --- |
| 最终SQLite整体套件 | 1577通过、0失败、88跳过；`unit-final.xml`与`unit-final.raw.out`。跳过原因为87项需专属PG及1项缺本地语义权重，非增加skip规避失败；严格PG另列，不合并历史数量。 |
| 严格PG原集合加新准入模块 | 17模块141通过，0失败/跳过；`pg-strict.xml`。使用CI相同顺序与命令形态。 |
| 真实进程hard-stop | 8通过，四窗口×两链全部执行；`pg-hardstop.xml`。 |
| JUnit门禁 | PASS，18模块149testcases、8hard-stop窗口；`pg-junit-gate.raw.out`。新增准入PG模块纳入工作流和独立列举的门禁测试合约，未减少任何原必需模块/反向断言。 |
| 迁移升级与模型对齐 | 专属空库完整upgrade head及alembic check均exit0，无新增模型漂移。 |
| 全前端检查 | 382通过、0失败/跳过；lint、typecheck、生产build均exit0，保留既有img warning。构建`BSPYXVhgdOQqMg9TMPvW-`。 |
| 全后端Ruff | exit0；`backend-ruff.raw.out`。 |
| 最终worker/清理目标补验 | 29通过，`resources/accepted-worker-private-read-final.raw.out`；含真实取消及超时、重复取消、损坏ZIP、失租、索引/提交失败、不确定COMMIT、成功来源保留、marker-only恢复。9个PG准入用例另纳入严格PG141，不再相加。移除owner锁的独立进程突变四竞争全部变红。早期30项为当时资源与JUnit组合范围，不冒充最终同一套检查。 |
| 依赖环境 | Python3.12.14，29条声明的精确pin与现有环境全部一致；Node22.23.1，复用既有锁文件匹配的node_modules，无安装/升级。不是新一轮干净安装。 |

精确命令与退出码：`postgres-checks.json`、`frontend-checks.json`及各子目录REPORT。测试只使用MockTransport/等效离线provider，所有环境关闭外部AI；无真实模型请求或费用，不改真实输出/人工判词/历史claim。

最终SQLite命令/退出码另见`unit-final-checks.json`，最终严格PG/hard-stop命令为`pg-final-checks.json`。PG执行源码记录为`pg-tested-source.json`（`7a76dd9`）；其后仅新增上述不属于严格集合的视觉测试体及标准库suppress导入，生产源码、fixture及所有严格PG用例字节未变，故复用其141/8结果而不重复启动测试库。前端源文件亦未受后续后端/测试变化影响，复用既有382项及构建，不重复安装。最终范围分别记录，不能理解为所有检查在同一次进程里执行。

## 页面及环境

新前端3134是上述接受构建，**页面测试的8112 API仍是之前已确认的专属合成环境后端，不冒充其已加载本轮预算/准入源码**。本批后端通过受控HTTP测试与PG套件验证；未重启已有API/正常站。前端可在`/growth/3b9ba85b-aed3-4e1f-9e17-6ced074828c5`核对私人草稿；需`backend/.tmp/complete-project-20261021/credentials.json`中的林舟学生账号，另一Mock账号对此任务404是正确隔离，不是数据丢失。本文不含口令。

真实渲染下草稿文字与未保存编辑可见；390px文档宽375，无整页横向溢出，截图见`draft/`。自动工具隐藏浏览器没有产生document.hidden事件，因此没有将它记为真实离窗通过；已交用户按正确账号切换标签后补验。63项生产workflow/SSR回归覆盖暂停/恢复、保存失败、任务与账号切换、迟到和乱序回执，不替代真实浏览器事件或首次独立用户验收。

PG资源仅本轮新建容器`careerproof-core-acceptance-20261022`、标签同名scope、loopback55445，数据库cp_ci/内部careerproof/alembic_check。没有宿主业务卷挂载；fixture独立cp_test_* schema并清理。迁移和worker配置在连接前核实该目标，未使用正常5432或既有55442预览库做本批PG测试。最终资源状态另见`resources.json`。

## 保留的边界

40000是保守字节准入值，不是实际token、费用或模型质量。更大请求仍可降级；工具规划可因最终预留不足而程序跳过，不承诺每份报告必调工具。已有`.env`若显式保留12000，不会被新默认覆盖；本轮未修改任何真实`.env`或重启正常服务。真正MiniLM权重语义效果、付费模型质量、真人首次使用及真实跨标签身份变化不由Mock或合成坐标测试替代。

容量是受管原件、保留解压文本和在途预留的逻辑总量，不含数据库/备份/日志等整个磁盘占用；失败释放预留但保留可重试原件。未知worker/旧无marker目录不擅自删除，需管理员另行核实。恢复工具默认dry-run，显式匹配数据库名和存储路径后才可apply，只回收无DB引用且进程/任务不再运行的独占目录；本轮只在测试存储验证，没有清理用户历史存储。

本地复现CI通过不表示GitHub已重新变绿；本轮不推送、不dispatch远端、不部署。既有其他执行端页面、材料选择器、指南/PDF、UUID旧helper、证据和P2 stash均保留，不批量暂存或清理。

最终结果汇总见`final-results.json`；最终源码为`ec1e5e5`，上述37份文件逐项匹配。专属55445容器已停止，两个测试库剩余cp_test_* schema均为0、卷保留；3134/8112继续运行供用户查看，其来源区别见`resources.json`。
