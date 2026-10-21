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

[isolation-proof.json](isolation-proof.json)证明旧隔离报告、投递、AI请求及用量行未变；没有新增AI attempt/usage。正常数据库未连接，正常站未启停，P2未触碰。内容与页面验收时隔离CareerProof服务在线；收尾再次核对，原46804/47000进程已不存在，8108/3108无监听且HTTP无法连接，原因未定，不把先前在线当作当前状态。未因状态消失自动重启服务；专属PG容器仍在运行，报告、业务演示SQLite、源码包和依赖保留。新业务演示进程已停止。

未验证：真实AI/Agent对本项目的语义分析、独立人员评价、生产部署、身份/授权/支付等项目外功能。11项行为测试不是CareerProof全量测试，桌面与390截图不是业务正确性或比赛完成证明。原三例、r7/r8安装阶段未重开。

## 后续：建表漏识别的最小修复

只改`backend/app/tools/code_analyzer.py`的SQL建表语法识别，允许可选`IF NOT EXISTS`，没有修改材料、评分公式或页面。新增真实SQLite执行与检测回归：旧规则3失败/2通过，修复后相关证据质量/上下文/数据库边界64通过；目标Ruff通过，初次格式检查失败原文保留。

在原专属PG上用原简历和项目版本生成新规则报告`4cd00c84-855f-4d26-8a3b-6fe31a076535`。新证据确实包含`campus_signup/schema.sql`第1—8行；29条证据再次与固定源码逐条匹配。旧报告/投递/AI请求与用量行不变。临时API使用空闲loopback端口，结束后已停止；没有启动正常站。

SQL状态由partial变为supported，是检测器修复后的结果差异，**不是用户补证或能力成长**；材料版本没有变化，不能冒充“补证→新版”验收。事务封装、取消方法等遗漏及通用建议仍未解决，等级仍受原规则局限。本节只关闭DDL漏识别，不签收整个业务理解。[真实新报告](sql-fix/report-after.json)、[前后对比](sql-fix/comparison.json)、[隔离与历史保持](sql-fix/result.json)、[红](sql-fix/red.raw.out)→[绿](sql-fix/green.raw.out)。

## 后续：实际运行回执补证链路（HTTP，页面随后补验）

为原SQL缺口创建`execution`类型任务，以修复后的`4cd00c84-855f-4d26-8a3b-6fe31a076535`为固定基准。V2 ZIP保留九个原文件的全部字节，只追加本次已产生的HTTP响应、pytest原始输出、源码摘要与说明；没有加入评测标准、期望答案或人为改写的结论，也不设置目标等级。运行回执来自本地合成环境，不伪装为独立审核或本人贡献认证。V1不变，原始失败记录保留。

既有API实际完成：创建补证任务→同项目上传第2版→保存材料选择→未授权外发的规则分析→读取任务和固定基准对比。补证任务`3b9ba85b-aed3-4e1f-9e17-6ced074828c5`状态为`compared`，新报告`5960cf5d-0f6a-4564-b7ca-037e17d743e3`。13个文件完成扫描，29条展示证据与V2原文及哈希一致，均属于新版本；历史报告、投递及AI请求/用量行保持原样。

**内容结果：五项等级全部未变。** pytest运行输出进入候选，SQL报告仍未选到事务运行回执，建议仍泛化。这不是“运行回执没上传”，也不能据此宣称业务内容已被系统充分理解；该限制应先于继续美化过程展示处理。比较由真实已有接口生成，没有手工填写对比结果。[补证任务](growth-runtime/growth-task.json)、[报告](growth-runtime/report-after.json)、[比较](growth-runtime/comparison.json)、[内容核验](growth-runtime/content-check.json)、[V2指纹](growth-runtime/v2-manifest.json)、[隔离保持](growth-runtime/result.json)。本机V2文件为`output/demo/CareerProof-campus-signup-v2-runtime.zip`。

本轮隔离后端通过受管会话45480/PID210292运行8108，HTTP完成后已主动结束；PG和数据保留。启动3108隔离前端被自动审批拒绝，工具只返回“blocked by policy”，未提供更具体原因。没有换入口或改命令绕过；本节没有页面、键鼠或390px补证走查通过结论。前述原报告页面截图不能替代新补证链路验收。入口记录见[growth-runtime/page-entry.json](growth-runtime/page-entry.json)，前端恢复前不宣称这些URL当前在线。

后续真实AI入口是现有`POST /api/v1/matches`，选择本项目岗位、合成简历和V2项目版本（见入口记录），另行明确外发授权后才可设置`externalAiConsent=true`。需要核对当前工具规划、可能的补检索/历史读取及最终分析的实际物理请求上限与预算；一次业务请求不等于一次模型请求。现有三例单步分析授权不覆盖该项目，本轮不发送、不预扣、不重置claim。当前仍无该完整项目的真实Agent语义结果，不以HTTP成功、Mock或未变化的规则等级替代。

## 后续：完整项目的Agent离线准入核对

[只读预检结果](agent-preflight/result.json)使用已保存V2规则证据、原13文件ZIP和当前生产函数：`build_evidence_contexts(max_evidence=2)`、冻结源定向搜索、`execute_retrieval_tool`及DeepSeekProvider的真实输入估算器。没有模型响应、HTTP请求、数据库写入或新Mock报告。初次探针只调用末端选取函数，遗漏工作流前面的冻结源搜索步骤，因此期望路径断言失败；已按生产顺序补齐该分支再核对，查询没有改变，生产检索代码没有为探针改动。这里不是全工作流执行或模型决策。

- 五项要求都有补取空间。人工指定`storage.py transaction connection.rollback`后，真实冻结源工具能补到`campus_signup/storage.py`21—30行（包含BEGIN/commit/rollback），原文逐行对应。只证明工具能返回该片段，**不证明模型会选择此查询或采信结果**。
- 真实provider估算器给出的最终分析输入保守上界：初始**22,610**，补入上述片段后**23,774**；本隔离环境当前报告输入上限为**12,000**。这不是供应商计费token数；但按现有本地门禁，完整五项上下文不能直接进入最终分析。不能现在发送一次后再把规则降级当作真实Agent成功。
- 当前工作流最多2轮工具规划、1次最终分析、至多1次结构修正；配置默认每次最多2次传输尝试，因此业务入口不等于1次物理请求。现有固定三例执行器还限制每例仅1个requirement，不能假装它已支持本项目5项要求，不能换上旧AG编号或重置旧claim来复用授权。

真实演示应是本项目V2、同岗位五项要求的一次已有工作流匹配：允许的只是当前材料的只读补检索、同owner同岗位历史（若明确纳入输入）及最终分析；不运行上传代码，不外发正常库材料。执行前必须先解决已证实的上下文预算准入，并为这一个报告明确物理请求总上限、重试、输出/费用上限和硬停证据，再核验执行日价格并获得单独授权。本轮没有提高配置，没有伪造“授权包已就绪”，也没有用缩成单技能的简化结果代替五项整体验证。

### 人工恢复已验隔离页面的现有命令

自动审批拒绝启动3108，暂不能完成新补证链路页面验收；以下仅供用户自行检查并执行，执行端没有改命令绕过。PG专属容器需已运行，8108和3108应空闲。不要在正常工程目录运行普通Start-Local来替代。

终端一（隔离后端）：

```powershell
Set-Location -LiteralPath 'D:\jbcode\web ai\jianli\backend\.tmp\agent-display-20261021\source\backend'
$env:PYTHONPATH = (Get-Location).Path
$env:AI_EXTERNAL_ENABLED = 'false'
$env:AI_PROVIDER = 'mock'
$taskPython = 'D:\jbcode\web ai\jianli\backend\.venv-dependency23\Scripts\python.exe'
& $taskPython -c "from urllib.parse import urlparse; from app.core.config import settings; u=urlparse(settings.database_url); assert (u.hostname,u.port,u.path)==('127.0.0.1',55442,'/cp_agent_display_20261021'), 'Wrong database: stop'; print('Isolated database verified')"
if ($LASTEXITCODE -ne 0) { throw '数据库检查失败，已停止启动' }
& $taskPython -m uvicorn app.main:app --host 127.0.0.1 --port 8108 --no-proxy-headers
```

终端二（原隔离生产构建）：

```powershell
Set-Location -LiteralPath 'D:\jbcode\web ai\jianli\backend\.tmp\agent-display-20261021\source\jianli'
$env:BACKEND_ORIGIN = 'http://127.0.0.1:8108'
& 'C:\Users\江博\AppData\Local\hermes\node\node.exe' 'D:\jbcode\web ai\jianli\backend\.tmp\agent-display-20261021\source\jianli\node_modules\next\dist\bin\next' start --hostname 127.0.0.1 --port 3108
```

恢复后可使用本机原凭据文件登录，打开`http://127.0.0.1:3108/growth/3b9ba85b-aed3-4e1f-9e17-6ced074828c5`核对固定基准、第2版材料和真实报告比较。代码/构建来源仍按前述隔离说明，不宣称最新HEAD全仓构建；两个进程都应留在各自终端，结束时仅停止这两个专属进程，不操作正常站。

### 用户手动恢复后的页面补验

用户已手动启动两个终端；本次核实8108/PID178520与3108/PID224728均监听loopback。没有由执行端重试被拒绝的启动命令，也未重建前端。读取既有隔离生产构建，BUILD_ID为`WDMAX7DoSVpEqnsSppkxf`，不是本次HEAD的全仓构建验收。

浏览器实际走查：固定基准报告SQL项展开补证入口 → 打开同一条已保存任务 → 打开已保存V2新报告 → 展开pytest来源。入口明确沿用既有任务，不重新填写；任务显示固定基准、V2版本及摘要、新报告链接和真实比较。pytest新增来源显示`runtime/pytest-output.txt`第1—8行；报告仍把它标为检索候选，未宣称独立认证或已执行上传代码。五项等级未变，SQL事务运行回执未进入该项来源、建议泛化的内容限制仍在。本次未点击上传、分析、投递或保存私人草稿，没有新建业务记录或模型调用。

1280×900及390×844实际视口下，补证页面和展开来源的新报告均无整页横向溢出：内容宽度分别1265与375（差额为滚动条）。步骤条为局部横滚，不能把其子项超出可见区判为整页溢出。页面控制台未观察到error。没有发现阻碍本次内容核对的展示问题，因此产品源码零改动；这不是完整键盘、首次独立用户或真实Agent语义验收。

证据：[检查记录](growth-runtime/ui-check.json)、[390尺寸](growth-runtime/mobile-geometry.json)、[桌面任务页](growth-runtime/desktop-ui.jpg)、[390任务页](growth-runtime/mobile-ui.jpg)、[桌面新版来源](growth-runtime/new-report-desktop-ui.jpg)、[390新版来源](growth-runtime/new-report-mobile-ui.jpg)。保存的DOM记录仅对应本次实际展开状态。用户启动的服务保持运行，本轮未停止其终端、正常站或专属PG；真实Agent上下文预算阻断仍按上节保留。
