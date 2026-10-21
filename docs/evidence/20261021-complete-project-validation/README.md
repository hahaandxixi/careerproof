# 完整项目材料验证（2026-10-21）

本轮按用户新方向停止扩展Agent页面、Mock展示及三例复核整理。验证结果是：**真实上传与来源定位成立，但现有规则报告不能充分证明已理解跨文件业务内容。** 没有新增模型请求，也没有把Mock报告作为本轮分析结果。

## 改动归属

起点main/`1d3a50e`。上轮汇报只列复核材料提交，没有同时说明工作区里仍有另一项Agent展示任务，信息不完整。具体归属如下；逐文件SHA见[ownership.json](ownership.json)。本轮结束再次核对11个Agent展示文件未改变，不一并提交。并行会话期间另有打包/日程文档提交，使用指南和当前接力底稿随之变化；原有工作区差异仍保留，不回退它们，最终现场见closeout-check.json。

| 文件 | 所属任务、用途 | 状态 |
| --- | --- | --- |
| backend/app/schemas/analysis.py、backend/app/services/analysis.py | 上一项Agent展示任务：只读投影四个已保存的跳过/降级原因，不改变工作流或评分 | 已跟踪文件有未提交修改，本轮保留 |
| backend/app/tests/test_agent_process_display.py | 上述投影的字段筛选/跨账号拒绝测试 | 未跟踪，本轮保留 |
| jianli/src/components/ReportAgentEvidence.tsx、jianli/src/lib/agent-evidence.ts | 上一项展示任务：将工具记录与实际引用、最终解释及补证入口关联，明确标注Mock | 未跟踪，本轮暂停且保留 |
| jianli/src/components/ReportDetail.tsx | 上一项展示任务：接入上述区块，替换旧折叠工具摘要 | 有未提交修改，本轮保留 |
| jianli/src/lib/api/domain.ts、jianli/src/lib/report-display.ts | 上一项展示任务：声明aiProcess、区分Mock报告标题 | 有未提交修改，本轮保留 |
| jianli/tests/agent-evidence.test.mjs、agent-evidence-render.test.mjs、fixtures/agent-evidence-report.json | 上述展示的纯逻辑、SSR测试和明确标注的Mock夹具 | 未跟踪，本轮保留 |
| docs/guides/使用与启动.md、docs/当前接力.md、JobDetailView.tsx、match-readiness.ts及其测试 | 更早已存在的账号说明、空白差异和岗位材料就绪提示；本轮不认领 | 原样保留，不并入本轮提交 |
| 75d6c59、1d3a50e | 中性字段定义及ZIP一致性核对 | 已提交，均不含上述Agent业务/前端源码 |

本轮新增范围仅为`demo/complete-projects/campus-signup-v1/`九个文件与本证据目录。没有修改CareerProof生产源码。

## 材料盘点与选择

- `demo/evidence-api/`：课程接口固定返回、数据库查询函数未接入路由，测试仅健康检查，不符合完整项目要求。
- `demo/market-scenarios/event-api/`：有重复/满额业务判断，但使用内存数组，无持久化或配套行为测试。
- `demo/market-scenarios/booking-quality/`：有真实HTTP状态断言，但仍为内存数据，无持久化和事务故障恢复。
- `demo/evidence-function-call/`、`demo/first-user/`：用于函数/材料版本演练，不是完整业务项目。

因此在独立演示目录原创补齐**校园活动报名服务**：FastAPI输入与HTTP边界→RegistrationService业务→SQLite参数化读写及事务→真实数据库文件；创建活动、报名、查询、取消均有实际行为。名额、报名和审计同事务更新，约束与异常处理见源文件。无登录/角色权限、支付、邮件或生产部署；取消后的原学生不能再次报名同一活动，其他学生能使用释放名额。这些是范围限制，不宣称完整招聘平台或商业上线。

源码入口：[项目README](../../../demo/complete-projects/campus-signup-v1/README.md)。本机可上传ZIP：`output/demo/CareerProof-campus-signup-v1.zip`；配套简历：`output/demo/CareerProof-campus-signup-resume.txt`。

## 先运行、后冻结、再评测

1. 真实模块行为测试11项通过，包括报名持久化、重复/满额/非法输入、取消只恢复一次、审计失败回滚、两个写入者争最后名额、参数化值；不只是函数声明或假返回。Ruff通过。两条既有依赖弃用警告保留，未升级依赖。
2. `run_business.py`通过CLI启动真实uvicorn进程并走loopback HTTP：201成功、404/409/422拒绝、真实SQLite触发器造成503，数据库名额和报名无半写；停进程后以同一SQLite文件重启，读取结果与文件SHA均一致。服务已停止，数据库保留在专属`.tmp/complete-project-20261021/`。复用dep23环境，不冒充干净安装。
3. `freeze_material.py`固定九文件和ZIP；SHA256 **56fa9fa10dccc035e20c5fa447077436d24f893cc20d0dea7cb0c01a15a3463c**。[清单](material-manifest.json)。读取报告后没有修改任何项目文件或上传第二版来调等级。
4. 在实际运行成功、冻结后，上传前写[独立于报告的评测依据](evaluation-plan.json)。核对具体业务事实，不预设目标等级；本表是执行端核验，不计独立真人评审。依据、预期检查、运行日志、数据库和答案均不在ZIP或检索库中。
5. `run_careerproof.py`通过既有HTTP注册专属合成账号、创建岗位、上传简历和ZIP、等待真实解析/扫描、创建`externalAiConsent=false`规则报告。没有改报告或证据表，没有注入预设输出。

原始命令对应脚本及`.raw.out`，结果见[business-results.json](business-results.json)、[source-verification.json](source-verification.json)。核验器首次将预览当成逐字节文件比较而失败；实际预览仅去掉末尾换行，已改为逐行核对，原文件哈希单独验证。未修改材料或产品以让检查通过。首次HTTP重启因端口TIME_WAIT失败，验证脚本改用每次独立空闲端口，原失败保留；首次Docker输出解码失败发生在HTTP写入之前，显式UTF-8后继续，原失败保留。

## CareerProof实际识别与遗漏

九文件均被扫描并可预览；29条报告证据的文件、行区间、内容哈希及材料版本全部与固定源码对应。完整函数及测试并非缺在上传包里。知识检索返回包含业务、存储、schema和测试的17个项目片段以及1个简历片段；本轮为本地hash向量，不称为语义模型理解。

| 岗位要求 | 实际输出与选取 | 核验结论 |
| --- | --- | --- |
| FastAPI接口及输入/异常 | supported/任务实现；api.py 36—38、22—56和依赖声明 | 确有完整路由与领域/数据库异常映射，但输入字段约束所在13—19未直接选入主引用；不能由框架工厂函数完整推断所有接口业务均完整 |
| SQL持久化与回滚 | partial/任务实现；service.py 25—54、storage.py 32—36、测试92—105 | 找到真实报名SQL、查询和故障测试，但没有选入storage.py 19—29的BEGIN/commit/rollback封装，也未选schema约束；没有完整说明跨文件事务链 |
| Python满额/重复/取消业务 | supported/任务实现；api.py工厂、__main__.py入口、service.py 5—7异常构造函数 | **选证存在实质偏差**：实际register 25—54和cancel 56—77未在该项引用中。引用源码是真的，但仅据这些片段不能证明全部指定业务，通用“存在Python函数实现”不是业务结论 |
| 行为测试 | supported/任务实现；测试29—39重启、14—16夹具、pytest依赖 | 看到了真实重启断言；重复、满额、取消、回滚、竞争等测试虽然都在材料里且已运行，却未由报告逐项对应。不能将测试源码存在说成系统执行了测试 |
| Redis查询缓存及失效（实际未实现） | gap/待核对检索候选；只返回两段README候选 | 没有错误认定缓存已实现，边界成立；但候选与Redis实现无关，建议仅“补直接相关材料”，不够具体 |

原报告的补证建议基本重复“仍需可核对的运行结果与验证记录，不能确认本人贡献”，Redis为“核对候选与要求的对应关系”。**未达到按业务缺口给出可执行补证计划的程度。** 系统未收到本轮运行回执，保留运行未验证的措辞本身合理；问题是没有结合已经提交的具体实现定位尚缺的验证。

## 可复现原因与最小后续方向

[detector-probe.json](detector-probe.json)直接调用本轮运行源码里的真实检测模块，无数据库或外发：

- `code_analyzer.py:507—560`按源代码顺序选每文件首个非空函数，`service.py`落到异常构造函数；同一文件/类型又在`:718`去重。它不是按该岗位的报名/取消业务选择方法。
- `code_analyzer.py:677`的SQL建表正则不识别常见`CREATE TABLE IF NOT EXISTS`。同样可在SQLite执行的两种DDL，普通形式识别、IF NOT EXISTS形式漏识别；本项目使用后者。控制样本只在探针内，不改冻结schema、不上传控制样本。
- `evidence_levels.py:144—154`可因某个实现片段的函数上下文完整而给“任务实现”，不等于已经验证复合岗位要求；`matcher.py:126—133`的supported依据技能检测强度，而非各业务要素逐一成立。

下一项应优先做**规则候选选择与评级含义的有界修复**：以本次冻结材料做回归，避免异常构造函数替代报名/取消；补DDL语法兼容；限制“单函数完整”被读成“整个业务要求完整”。不靠扩大材料权限、改变上传内容或批量提高等级。跨文件业务语义理解仍需另行真实AI授权与结果核验，本轮不据规则输出宣称已完成。

页面在内容检查之后仅补验：1280与390视口，规则模式标识、展开实际Python引用及锚点定位均可用，文档/正文未横向溢出，代码区自行横滚。没有发现阻碍本轮内容核对的页面故障，因此**没有继续Agent区块或其他产品页面修改**。截图仅证明可查看，不证明结论充分。[桌面完整页](desktop-report-full.jpg) / [390引用](mobile-python-evidence.jpg) / [尺寸记录](page-geometry.json)。首张桌面窗口捕获被侧栏裁成668px宽，保留为捕获限制，不冒充1280完整图；随后浏览器fullPage捕获为1265px内容宽，差额是滚动条。

## 入口、隔离与剩余范围

报告：<http://127.0.0.1:3108/reports/c97cdfa6-b87e-4143-9551-f780012648aa>。浏览器当前是本轮合成学生；重新登录的账号获取入口为本机`backend/.tmp/complete-project-20261021/credentials.json`（不提交、不打包、不打印密码）。

打开报告→逐项证据→Python项“查看8条来源证据”，能直接看到这次错误偏向入口/异常类的选证；SQL项看报名SQL与回滚测试。预览项目时九个文件均可读，能与报告遗漏对照。这里没有Fake Agent或预设报告。

复用已分配的隔离容器`careerproof-agent-display-20261021`、PG `cp_agent_display_20261021`/55442和8108/3108服务，不与正常库混用；本轮新增独立合成账号、岗位、材料和规则报告。运行源为75d6c59加上原Agent展示未提交的只读投影/前端，精确范围见归属表；没有据此声称HEAD构建或候选全绿。新规则报告不触发Agent展示面板。

[isolation-proof.json](isolation-proof.json)证明旧隔离报告、投递、AI请求及用量行未变；没有新增AI attempt/usage。正常数据库未连接，正常站未启停，P2未触碰。隔离CareerProof服务保留供查看；新业务演示进程已停止，数据库与源码包保留。

未验证：真实AI/Agent对本项目的语义分析、独立人员评价、生产部署、身份/授权/支付等项目外功能。11项行为测试不是CareerProof全量测试，桌面与390截图不是业务正确性或比赛完成证明。原三例、r7/r8安装阶段未重开。
