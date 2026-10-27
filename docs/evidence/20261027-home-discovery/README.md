# 匿名首页与技术岗位发现候选

核实日期：2026-10-27。本轮实现已经提交，**工程检查通过，最终浏览器验收未完成**。不计为首次独立用户验收，也不代表真实 AI 效果通过。

## 版本与范围

- 基线：`365aecffd5ef1807b993829bfba8bc6d02289fa8`，包含学生四项主导航和不强制创建补证任务的流程。
- 服务端提交：`f872444a8a41a9e96ba94f7fc679dda59d90e350`。
- 前端提交／本轮产品源码：`a95eb4eadb886514f24cee6ae23db0761ad8a585`。
- 分支：`codex/home-discovery-20261027`；[草稿 PR #5](https://github.com/hahaandxixi/careerproof/pull/5)以 `codex/report-workspace-20261026` 为基线，依赖 PR #1；未修改、合并 PR #1 或 main。
- 精确接受文件及 Git blob、工作区 SHA-256：[candidate.json](candidate.json)。共22个代码／测试／分类配置文件；新增文档不改变产品源码。
- 原主工作区仍为 `8ca91cc`，48项已跟踪修改、1587个未跟踪文件保持原样；不把它们纳入本候选。

## 用户实际得到的变化

| 原实现 | 本候选 |
| --- | --- |
| 首页只有一块固定的合成证据预览，匿名导航另有重复示例入口 | 保留现有主标题、两项操作，预览增加岗位匹配／补证建议／版本对比三个手动标签；匿名导航仅岗位发现、登录、注册 |
| 发现页使用五个粗粒度旧分类 | 首页与发现页共用七个技术方向、对应二级标签；城市、工作类型、语言、关键词独立组合 |
| 首页没有可衔接筛选的真实岗位区 | 首页读取服务端前3个结果，查看更多保留筛选并进入 `/jobs`；发现页每页12项 |
| 关键词只查标题、企业、描述 | 同时检索已保存岗位要求的技能名和原文，计数与分页使用同一谓词 |
| 手机筛选逐项纵排较长（早期构建的实际观察） | 最后调整为两列筛选，按钮占一行；此最终样式仍待浏览器复验 |

岗位卡只展示真实保存的标题、企业、城市、工作类型、要求数量和技能标签。`isDemo=true` 明确显示“合成示例岗位”；没有薪资、收藏假按钮、企业认证、在线状态或匹配百分比。已有“按材料推荐职业”继续保留独立入口。

## 分类与旧数据

唯一人工维护来源是 [technical-careers.json](../../../backend/app/data/technical-careers.json)，前端 JSON 是其生成副本；修改后运行 `python scripts/sync_technical_careers.py`，`--check` 和回归测试检查一致性。没有新增数据库字段或迁移，也不回写旧岗位分类。

| 七个方向 | 可用二级标签 | 与旧类别的关系 |
| --- | --- | --- |
| 后端开发 | Java、Python、Go、Node.js、C/C++、全栈 | 明确角色标题优先；仅在无角色线索时采用单一明确后端框架 |
| 前端与移动 | Web、React/Vue、Android、iOS、鸿蒙 | 明确角色标题优先；仅在无角色线索时采用单一明确前端框架 |
| 测试与安全 | 软件测试、自动化、测试开发、性能、安全 | 角色标题决定；不能因会 Python 就判作后端 |
| 数据工程 | 数据开发、分析、仓库、ETL、治理 | 明确标题，或旧 `data_analysis` 类别作为兜底 |
| AI与算法 | 大模型、机器学习、NLP、视觉、算法 | 依据明确角色标题，不凭任意描述里出现“AI”归类 |
| 运维与云原生 | DevOps、云计算、Kubernetes、运维开发、DBA | 依据明确角色标题；旧 `operations` 不自动等同技术运维 |
| 产品与技术协作 | AI产品、数据产品、需求分析、技术项目管理 | 明确产品／协作角色优先，避免被其技术词误归后端或算法 |

旧 `software`、`operations`、`design`、`other` 不能一对一变成七个方向。冲突框架、通用标题或没有充分线索的岗位保持“未细分”，在“全部岗位”和旧分类链接中仍可查询。技术方向仅用于导航，不是能力判断；二级标签和语言还需实际标题或技能支持。英文词有边界，Java 不匹配 JavaScript。框架与语言导航不是完整职业语义分类器，漏归类时优先保留未知。

参数：`direction`、`specialty`、`language` 使用集中白名单；二级标签必须属于所选方向。`city`、`employmentType`、`q`、旧 `category` 和 `page` 继续支持。无效导航值安全回退；切换方向保留其他条件并回到第一页。`full_time` 仍显示“全职”，未改为“社招”。服务端在分页前筛选，空集回到第1页，超出最后一页按实际页数夹取，不做当前页局部过滤。

## 三种预览的真实性

- 岗位匹配复用既有 `HEATMAP_DEMO[0]`、`DEMO_LABELS` 和证据状态颜色；不新增 AI 评级或实际分析结果。
- 补证建议是通用的核对工程→完善直接证据→上传新版并主动分析的操作说明，不要求先建任务。
- 版本对比是明确标记的概念示意，没有真实报告ID或伪造变化、等级与执行结果。
- 没有自动轮播、计时器、大型依赖、真实模型请求、自动报告或投递写入。用户手动点击或键盘方向键切换，面板具有相应 ARIA 关联。

## 本地自动检查

环境：Windows，Python 3.12.14、Node 22.23.1、Next 15.5.27、React 19.0.0。复用已验证依赖目录，未重装或升级依赖；这不是干净安装验收。

命令均在本独立工作树执行；前端命令工作目录为 `jianli/`，后端默认项目根，`alembic` 工作目录为 `backend/`。日志保留真实输出。

| 命令／检查 | 退出码与结果 | 证据 |
| --- | --- | --- |
| `npm test` | 0；486通过，0失败、取消、跳过 | [完整输出](frontend-full-final.raw.out) |
| `npm run typecheck` | 0 | [输出](typecheck-final.raw.out) |
| `npm run lint` | 0；0错误，保留鉴权图片既有1条 warning | [输出](lint-final.raw.out) |
| `BACKEND_ORIGIN=http://127.0.0.1:8140 npm run build`（PowerShell设置环境后执行） | 0；首页123kB、发现页119kB首次加载JS；未新增依赖 | [输出](frontend-build-final.raw.out) |
| `python -m pytest backend/app/tests/test_job_discovery_filters.py backend/app/tests/test_jobs_api.py backend/app/tests/test_job_discovery_curation.py -q --basetemp=backend/.tmp/jobs-regression-final --junitxml=backend/.tmp/backend-jobs-final.xml` | 0；22通过，0失败／跳过 | [日志](backend-jobs-final.raw.out)、[JUnit](backend-jobs-final.xml) |
| `python -m pytest app/tests/test_job_discovery_filters.py -q --basetemp=.tmp/pg-final --junitxml=.tmp/postgres-taxonomy-final.xml`（在backend运行，专属PG；日志含实际绝对路径） | 0；4通过，0失败／跳过 | [日志](postgres-taxonomy-final.raw.out)、[JUnit](postgres-taxonomy-final.xml) |
| `python -m ruff check` 本轮7个Python文件 | 0 | [输出](ruff-final.raw.out) |
| `python scripts/sync_technical_careers.py --check` | 0；前后端分类一致 | 分类一致性也由上述真实回归检查 |
| `python -m alembic upgrade head`、`python -m alembic check` | 各0；专属PG，无待生成迁移 | [迁移](migration.raw.out)、[对齐](migration-check.raw.out) |
| 实际8140 API，6组只读GET | 全部200，数量与方向组合、旧值兜底一致 | [逐例结果](live-api-filter-check.json) |

后端运行显式设置 `PYTHONPATH` 为本工作树的 `backend`、`APP_ENV=test`、`AI_EXTERNAL_ENABLED=false`、`AI_PROVIDER=mock`。PG运行从本机忽略目录读取该任务专属连接并设置 `CP_HOME_TEST_DATABASE_URL`，测试在连接前检查主机、55447端口和两个明确的任务库名，拒绝其他目标；不把包含密码的连接串贴入命令或证据。

回归覆盖：七方向真实HTTP查询、混合技能未知兜底、二级标签／语言／城市／类型／关键词组合、要求原文检索、计数与分页一致、最后页与空集、隐藏／草稿排除、企业管理权限；前端覆盖URL恢复、无效值、旧链接、迟到请求、错误重试、分页夹取、首页联动、真实组件场景切换与角色导航。组件级受控测试不冒充浏览器键盘／登录验收。

## 运行绑定

[runtime.json](runtime.json)记录进程、目录、端口、数据库和最终构建。

- 前端：`http://127.0.0.1:3140/`；最终构建 `S9wXSiHUIGmqeSjj9xqR3`，产品源码 `a95eb4e`；独立 `home-discovery-20261027/jianli`，原预览不变。
- API：`http://127.0.0.1:8140`；同独立工作树后端，外部AI禁用。后端生产文件在启动后没有修改；测试变化不影响进程内容。
- 数据库：容器 `careerproof-home-discovery-20261027`，本机55447，预览库 `cp_home_discovery_test_20261027`；最终PG回归使用另一专属库 `cp_home_discovery_regression_20261027`，没有重置预览库。
- 存储：本工作树 `backend/.tmp/storage`。预览仅导入既有 `demo/market-scenarios.json` 的三套合成岗位，其他分类真实为空。凭据只在本机忽略目录生成，未入Git或证据。
- 本轮仅停止、重建和启动自有3140前端；没有操作3138/3139、8114或正常业务库。

## 浏览器观察、阻断与待验步骤

Edge曾实际打开早期构建 `xrJlPRtZfz-qWoD7K3gGS`，确认匿名首页、三种标签、七方向、服务端返回的三套合成岗位真实渲染；实际CSS宽度1600和434下未观察到整页横向溢出。两张工具即时截图属于早期未固定补丁，**不作为最终候选截图**，也未冒充用户参考图。

浏览器原有90%缩放使请求的1440／390视口实际成为1600／434。随后尝试读取Windows浏览器窗口以核对原生缩放，工具因不能可靠识别当前URL而终止本轮Computer Use。此后未重试或换接口控制浏览器。没有修改原缩放；临时视口覆盖的复位未能确认。

因此1440、1280、768、390、真实200%、最终两列筛选、Tab/Enter/Escape、页面筛选回退／刷新及学生／企业真实登录仍为**待浏览器验证**。无可交付的最终截图，不宣布页面验收通过。

最小补验（可直接在3140执行）：

1. 浏览器菜单先设100%，依次检查上述四宽：Hero单列、三场景可读、方向可横滚、筛选紧凑、卡片单列／多列且无整页横向溢出；保存对应构建截图。
2. Tab到场景标签，左右键、Home/End、Enter核对单面板与焦点；Escape不应触发任何业务行为。切三种预览不应创建报告或请求模型。
3. 后端→Python，城市杭州、实习、Python语言，查看1条真实结果；查看更多带条件进入发现页，刷新、后退应保持条件。AI方向应为空，重置回到3条。旧 `/jobs?q=React` 仍应找到前端岗位。
4. 从岗位卡进入要求详情，未登录分析应按原流程登录；登录合成学生／企业分别核对原工作台，学生主导航保持4项，企业管理与授权入口不变。不要用新建任务绕过流程。
5. 用浏览器原生菜单设200%，检查内容、按钮、横滚与焦点；拍正常／200%截图后恢复原设置。在实际减少动效偏好下再次切换标签和方向。

这是执行端页面验收，不替代独立用户走查。报告、固定快照、私人草稿及真实模型效果本轮未重新验收，相关旧边界保留。

## 集成与后续交付

[源码CI 40373258950](https://github.com/hahaandxixi/careerproof/actions/runs/40373258950)绑定 `a95eb4e`，三个任务全部成功：前端486通过；SQLite整体1590通过、94跳过、0失败；PostgreSQL严格集合141通过，强停8通过；JUnit门禁和迁移对齐成功。精确任务ID与原始日志摘要见[ci-source.json](ci-source.json)。后续仅文档提交不改变上述产品源码，最新分支检查以PR为准，不把不同提交的数量相加。

本轮改动与PR #1重叠首页、导航及样式，故明确依赖其基线。PR #2其他未接受前端成果若后续集成，需要逐文件复核这些重叠处，不能把另一工作树整体复制进来。PR #3材料和PR #4历史归档均未合并。

PDF、视频、源码ZIP没有为此候选更新；它们仍需在页面补验与最终接受范围确定后绑定同一提交。保留原交付物、历史报告、模型回执与人工原表。

## 10/27 岗位搜索、角色入口与合成授权演示

本节产品源码为 `b481307`，继续在 `codex/home-discovery-20261027`；不合并main或其他PR。上文三岗位、AI方向为空及浏览器受限等描述是早期快照，不适用于本节预览。

- 搜索改为岗位标题、明确技能和企业名称；明确方向词复用现有分类表达式，不再搜索描述和要求正文的协作措辞。“后端”修复前返回Python与React，修复后为Python与新增Java，不再返回React。技术词Java不会匹配JavaScript。
- 推荐入口仅向已登录学生显示“按我的材料推荐岗位”；企业、管理员、匿名隐藏。学生推荐页面实际可访问；现有材料规则推荐接口实际返回全部9个候选。
- 原三份场景对象逐字段与改前Git内容一致；新增六份，每份5条要求。9个岗位覆盖七方向：后端2、前端与移动2、其余各1。六个新岗位仅提供岗位要求，不伪造专属下载材料。
- 在原专属合成库生成3份真实规则报告并经`POST /applications`明确授权；Python岗位2份，React岗位1份。Python实现材料3项有项目证据，仅声明材料0项；不代表运行或本人贡献核验。未插入预设报告、未改分或生成企业回复。
- `evals/seed_market_applications.py`校验固定数据库、存储、容器标签、绑定端口、API与库中企业身份，复用材料上传与规则流程。企业读取经过显式`/view`，因此演示投递当前为“已查看”，产生的站内事件仅涉及合成账号。完整重放前后岗位、材料、报告、投递与事件数相同；历史报告保留。
- 本地定向命令：`pytest app/tests/test_job_discovery_filters.py app/tests/test_job_discovery_curation.py app/tests/test_market_applications_seed.py -q --basetemp .tmp/search-green-20261027 --junitxml=.tmp/search-green.xml` → 23通过；`node --test tests/job-discovery.test.mjs tests/scenario-materials.test.mjs` → 16通过。目标Ruff、ESLint、TypeScript与生产构建通过。未运行全量后端。
- 真实PG/API核对：9岗位／七分类、10组关键词、学生材料推荐9候选、导入与投递重放无新增、企业计数2+1、同岗位分页与Python支持/声明筛选各1、无关学生访问404。首次脚本误用不含报告的detail GET曾失败，修为原有显式view入口后成功；未绕过授权。
- 前端3140构建`hhVsGvCYGjmQvDXKP92Sx`，API8140，同库`127.0.0.1:55447/cp_home_discovery_test_20261027`，存储仍为本工作树`backend/.tmp/storage`；外部AI禁用。桌面1440与手机390实际截图位于本机`output/screenshots/CareerProof-market-polish-20261027-b481307/`。企业入口隐藏、学生入口与推荐页、候选热力图、固定来源及筛选均实际操作。

运行准备（仅本机已确认的独立预览）：从本工作树`backend`运行`python -m evals.seed_market_applications --runtime .tmp/private-runtime.json`。私有凭据与可恢复状态只留在Git忽略目录，不随交付公开；工具拒绝正常业务库。真实AI效果、首次独立用户与原生200%仍不由本次验证替代。

## 10/27 职业规划失败提示

接受源码`b137997`（后端修复`a3681b1`）。3140前端构建`9zU9zGtLYlLKVrZtrCrFV`，API8140、原专属合成库和存储保持不变。实际服务日志确认`provider=mock external_ai_enabled=False`，没有切换DeepSeek或读取/展示完整模型密钥。

- 根因：Mock provider被当成异常，宽泛catch统一标成`model_unavailable_or_invalid`；无法运行模型却持续保存规则降级规划。现在明确返回`external_ai_disabled`或`mock_provider`，不新增规划、不替换历史；按钮旁显示原因并阻止相同配置下继续点击。
- 模型路径仅记录安全阶段、异常类、原因枚举与HTTP状态；区分配置、网络、超时、额度、JSON/长度截断、字段结构及业务引用校验。原有引用、事实、归因校验和数据库故障传播保留。已发送请求的真实失败仍保留降级及用量记录。
- `max_tokens=1500`保持不变：未获得/执行新的真实模型请求，不能把此次Mock配置故障归因于截断。离线长度停止和结构失败分支可正确识别；最初两个探针用的单左括号可被现有JSON修复机制解析，已改为真正未闭合的字符串输入。
- `pytest app/tests/test_career_plan_failures.py app/tests/test_career_change_attribution.py app/tests/test_career_visible_checks.py app/tests/test_frozen_career_conflict.py -q`：97通过；职业规划前端两个定向文件10通过；目标Ruff、ESLint、类型及生产构建通过，未运行全量测试。日志/JUnit留于本工作树`backend/.tmp/career-failure-*`。
- 实际接口两次提交均为`external_ai_disabled`、`planId=null`、保留9个规则候选，规划记录4→4；原快照哈希与上次规划完全不变。真实页面已验证按钮禁用、原因只显示一次及“本次规则候选（未保存为规划）”。截图在本机`output/screenshots/CareerProof-career-ai-fix-20261027-b137997/disabled-ai.png`。真实DeepSeek效果、额度和真实输出截断仍未复验。

## 10/27 企业标签页选中状态恢复

产品源码 `2775029088fb2cdce9c3a9b2feb4ba7416afa4d1`，仍在原独立工作树和分支。离窗曾执行破坏性 clear，回窗只重读列表；现在区分 suspend/resume 与明确清除。候选、岗位要求、引用展开和对照选择仅留页面内存，隐藏时不渲染报告；返回先用 GET 列表及必要的 GET detail 核对权限、报告和岗位身份，再复用已明确打开的固定快照，不自动 POST view。撤回、读取失败或报告身份变化清除相应选择；换身份/卸载丢弃缓存。未发送回复及确认仍清空，本轮没有发送回复、AI请求或更改后端。

- 修改：ApplicationBoard、application-board-session；SkillRadar仅增加可选的选中/引用展开状态回调，未重构雷达或改变其他调用方。refresh-gate原有合并闸门保留，session合并在途核验，局部保留高度避免报告临时卸载导致页面塌陷；不运行滚动或锚点定位命令。
- 红：新增用例在原session上因缺少suspend失败。绿：`node --test tests/application-board-visibility.test.mjs tests/application-board-session.test.mjs tests/refresh-gate.test.mjs tests/skill-radar.test.mjs tests/skill-radar-render.test.mjs tests/history-enterprise.test.mjs tests/failure-reply-draft.test.mjs tests/verification-reply-draft.test.mjs`，64通过/0失败/0跳过，exit 0。包含真实Workspace处理器的模拟事件验证：授权前无报告、要求与引用展开恢复、两人对照恢复、撤回剔除、草稿及确认清空；session验证并发合并、旧回执失效、只GET恢复且open次数不增加、卸载清除。模拟事件不充当真实标签切换。
- `tsc --noEmit`、五个目标文件ESLint及`next build`均exit 0；目标lint无警告，未运行全量前后端。原始红/绿及检查输出留本机忽略目录 `backend/.tmp/board-resume-*.raw.out`。
- 3140已从接受提交启动，构建`Zs6bc13o3xglTwcRB-LTv`；8140后端、55447专属合成库与storage保持不变。非正常业务库，无浏览器持久化。
- 真实桌面补验未完成：Edge扩展能读取工作台，但获取本机Edge窗口时工具因无法可靠确认当前网址而停止；遵守停止，不换接口绕行。没有最终截图或真实滚动保持结论。请在3140打开候选、选要求并展开引用，勾选两位并排核对，切到其他真实标签再返回；确认自动恢复、滚动不跳、回复草稿清空且发送仍需手动确认。快速重复切换检查相同状态。撤回和身份变化拒绝已由定向回归验证，未对原演示投递执行撤回操作。
