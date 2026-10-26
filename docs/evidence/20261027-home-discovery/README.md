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
