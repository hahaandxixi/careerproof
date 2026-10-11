# 传智杯30：AI补证建议来源一致性与可执行性审查（audit）

2026-10-11。审查人：ZCode（Start Plan / Weekend Build，GLM-5.3-Flash 会话内分析，全程零 provider 调用、零联网、零数据库/服务/浏览器）。Git 根 `D:\jbcode\web ai\jianli`，HEAD `3d76a5b`（卡面基线 ff0c170 的唯一下游提交，仅 docs）。本文件与同目录其余文件为本次唯一写入面；生产代码、测试、盲评标签与评分零修改。

## 0. 一屏结论

- **生产契约对 8 例盲评草稿：6 接受、1 拒绝、且该拒绝纯属词面巧合**。接受与拒绝都不构成对独立盲评失分的语义复核：结构合法 ≠ 语义可靠（卡面原话），本审查证明的是二者差异可复现、且失分点在生产路径上"不可见"或"不可表达"。
- **最重要 3 处可复现差异**：① b294018f1c 空话计划结构合法通过（守卫只认"满足"不认"符合"）；② 09fb4e82f3 共用账号来源对生产上下文不可见、注入候选后契约仍接受（且 `test_task_boundaries.py:98-107` 已钉死"未来补交"形状允许）；③ e2fd108ad9 的"源码存在=线上稳定"推断本身零 flag，拒绝仅来自步骤措辞"代码…已通过"命中词面模式，换中性措辞后"已部署接口证明"整套通过。
- **下一有界实现建议只做 1 项守卫扩展（e2fd 形状）+ 1 项窄来源锚定规则（共用账号提取形状）**，均为保守新增拒绝（进入既有一次修正→整体回退链路，不改降级行为）；lru_cache 机制可行性与"键设计"需求覆盖属语义判断，只能人工核对/提示词引导，不做关键词规则（卡面禁止冒充）。
- 独立盲评分数（humanReview=false，作者合成草稿）不是网站真实输出，本审查未将任何分数写回或当作生产基线。

## 1. 范围、方法与映射决策

### 1.1 只读面

冻结输入 `backend/evals/quality-blind-plan-review-input.json`（SHA256 `a7418dbd…50ac5e`，与 review.json 声明一致）、`docs/evidence/20261010-AI-blind-plan-review/review.json`、`codex-review.md`。生产路径只读：`backend/app/agents/contracts.py`、`evidence_workflow.py`、`provider.py`、`backend/app/tools/{matcher,code_analyzer,task_boundaries,function_coverage,evidence_levels,hybrid_retrieval,semantic_retrieval,skill_rubric,resume_parser}.py`、`backend/app/tests/test_task_boundaries.py`。全部 hash 见 manifest.json。

### 1.2 探针（纯离线、真实现行生产函数）

`probe.py`（存档于本目录，可执行副本在 `backend/.tmp-plan-audit-30/`）：对 8 例逐个执行

1. 真实 `match_candidate`（matcher.py:60）——用案例原始 requirement/resume/personalFiles/referenceFiles 构造 `RequirementInput`/`SkillClaim`/`ProjectFileSnapshot`，得到**真实 verdict、rule_score、evidence_list**；
2. 真实 `build_evidence_contexts`（evidence_workflow.py:78）——得到真实 `RequirementEvidenceContext`（含 rating_ceiling）；
3. 草稿作为 `task_plan` 塞入 `AIRequirementAnalysis`，走真实 `validate_grounded_analysis`（contracts.py:272）；
4. 逐守卫分解（task_boundary_error / unsupported_attribution / overclaim_flags / redundant_source_request / runtime_plan_without_implementation_step / execution_plan_skips_explicitly_missing_implementation）+ 定向变体。

`probe2_source_visible.py`：对 09fb4e82f3 用 `match_candidate(semantic_candidates=…)` 注入 `semantic_document_candidate` 形状候选（semantic_retrieval.py:169 的真实输出形状），证明"来源可见时契约是否设防"。

两次运行 exit=0、stderr 0 字节；原始输出见 `probe-results.json`、`probe2-source-visible.json`，命令与 hash 见 `probe-commands.out`。

### 1.3 映射决策与偏差声明（诚实边界）

- **外圈文本固定**：8 例共用的 explanation / information_gap / suggestion / summary / rating 均为固定中性文本（探针源码常量），唯一变量是草稿计划本身。这样契约命中/放行可直接归因于计划文本。
- **claim 映射偏差**：resume → `SkillClaim(skill, claim_text=resume)` 直接构造，未走真实 resume 解析。核对 SKILL_KEYWORDS（resume_parser.py）后：853352704e（Redis："redis|缓存"）、f5c5e00efe（内容运营）、0f2a863462（SQL）三例与真实解析一致；**09fb4e82f3 的 resume"参与过后端开发。"不含 "python"，真实解析不会提取 Python 声明，verdict 将是 gap 而非 claimed_only**。该偏差不影响计划守卫结论：claimed_only 与 gap 在 validate 中同属"必须填 gap/suggestion + 禁个人引用"分支（contracts.py:315-321），且该例 evidence 为空，守卫行为两 verdict 下相同。
- **rating 构造**：rubric_for 恒非空 → validate 必然要求 rating；按真实 `_rule_classification` 上限构造结构性一致 rating（评级维度本身非本审计对象，传智杯25 已有结构套件覆盖）。所有案例 rating 均通过校验，未污染计划守卫结论。
- **Production 上下文比盲评来源视图薄**：matcher 对 .py 只捕获 `def` 行（metrics.py/cache.py 的 snippet 仅 1 行），对无文档 rubric 技能（Python/Redis/SQL）的 markdown 捕获 retrieved_context 行级候选（README 2 行、content_plan 1 行、notes 1 行）。盲评读到的是完整文件。这是系统性差异，见 §3。

## 2. 每例对照表

分数顺序 [sourceCompliance, deliverableNamed, stepsExecutable, checksObservable]，引自 review.json summaryForCodex。

| case | 盲评分 | 真实 matcher 来源状态 | 生产契约 | 为什么（探针实测） | 误判风险 |
|---|---|---|---|---|---|
| 37882b616f | 2,2,2,2 | supported / python_code `def total(values):` 1 行，ceiling=2 | **接受** | 六类守卫全空；变体无 | 低。但上下文仅 def 行，TypeError 分支不在上下文——"异常与源码校验一致"核对的是上下文外行为，人工属性 |
| 45c8ae3412 | 2,2,1,1 | supported / `def cache_get(key):` 1 行，ceiling=2 | **接受** | 计划无"运行/执行/输出"类词 → `runtime_plan_without_implementation_step`=False（contracts.py:122）；lru_cache 装饰器行未入上下文，机制缺口对契约不可见；变体 v1（去"补充写路径"步骤、留"直接运行并验证"）仍**接受**——因 cache.py 片段无"Python…未实现"语句，explicit_gap 前提不成立 | 中高。生产 verdict"存在Python函数实现"高估来源（lookup 未定义）；用户按计划执行会卡在失效机制。属"只能人工核对"（§4-C） |
| b294018f1c | 1,0,0,0 | supported / 同 37882b616f | **接受** | 空话无任何 flag。关键：检查"材料**符合**岗位要求"不命中 ability_claim 模式 `满足.{0,25}(?:岗位\|要求)`（contracts.py:225）；控制变体"材料**满足**岗位要求"被拒（"unsupported ability or execution claim"） | **最高**。结构合法的零信息计划直达用户；"符合/满足"一词之差决定生死，证明该守卫是词面不是语义 |
| 09fb4e82f3 | 0,2,0,1 | claimed_only / **evidence=[]**（group_report.md 对 Python 零命中：无 .py、无文档 rubric，code_analyzer.py:161-167,375）| **接受** | 来源不可见 → 任何来源锚定守卫拿不到"全组共用账号，未区分作者"。probe2 注入候选后**仍接受**：`_ATTRIBUTION`（task_boundaries.py:7-14）要求"参考/小组材料+作为/当作+本人贡献"形状，草稿"筛出本人署名的提交"不匹配；task_boundaries.py:39 还显式豁免"本人具名的提交记录"；`test_task_boundaries.py:98-107` 钉死"共用账号来源+未来补交贡献证明计划=允许" | **高**。用户按计划去筛不存在的署名提交。生产两层都不设防：抽取层看不见、契约层看见了也不匹配（§4-B） |
| e2fd108ad9 | 0,1,0,0 | supported / `def total(values):` | **拒绝**（唯一拒绝例） | 拒绝错误串：`AI analysis contains an unsupported ability or execution claim`——来自步骤"将**代码**文件当作**已通过**运行测试的证据提交"命中 execution_claim 模式（contracts.py:229-230，经 contracts.py:345-348 应用）。**核心语义主张不受检**：验收"源码存在即证明线上接口稳定运行"零 flag；变体 v1（步骤换"整理 metrics.py 源码文件"，保留交付物"已部署接口证明"与该验收）**接受** | **高**。契约挡住的是措辞巧合，不是"源码存在≠部署/稳定"这一推断本身（§4-A） |
| 853352704e | 2,1,2,2 | claimed_only / retrieved_context×2（**含"Redis 未实现，当前只有缓存需求说明。"行**），ceiling=1 | **接受** | `execution_plan_skips_explicitly_missing_implementation` 真的识别出 explicit_gap（"Redis 未实现"，contracts.py:160-174），但步骤"**编写**含连接与**读写**的最小客户端代码"满足 implementation_step 正则（contracts.py:123-128）→ 不拦截。变体 v1（只留"本地运行并保存…"，删编写步骤）**被拒**："requests execution before missing implementation" | 中。守卫粒度是"有没有任何实现动词"，无法检查实现是否对症；需求标题"说明键设计"被完全遗漏——生产无需求覆盖检查（§4-D）。评级侧 ceiling=1 正确压级 |
| f5c5e00efe | 2,2,2,2 | claimed_only / retrieved_context×1（复盘行），ceiling=1 | **接受** | 无 flag。document_structure 未生成（受众/用户群 rubric 行缺失 → code_analyzer.py:479 `len(assigned)<3` 返回空） | 低。生产上下文只见源文件 5 行中的 1 行，计划的渠道/指标对齐在生产不可见——无矛盾，仅可见性差 |
| 0f2a863462 | 2,2,2,2 | claimed_only / notes 候选 + 3 条 **provenance=reference**（sql_schema/sql_query/retrieved_context） | **接受** | 无 flag；reference 隔离正确（不进 portfolio 引用集合）。`runtime_plan_without_implementation_step`=True（"执行记录"含"执行"且"编写统计查询"不匹配名词表）但 explicit_gap 前提不成立 → 不拦截 | 低。反证价值：同款"查询文件作者可定位为本人"作者归属措辞在无共用账号来源下合法——正是 §4-B 规则的负例锚点 |

**对照总结**：盲评 4 类失分模式 × 生产可见性——笼统空话（b294018f1c）：结构上不可见；与来源矛盾（09fb4e82f3、e2fd108ad9）：前者来源不可见+形状不匹配，后者只挡词面巧合；机制缺失（45c8ae3412）：装饰器行未入上下文且机制可行性非结构概念；需求覆盖不全（853352704e）：生产无需求覆盖检查。**盲评的 4 类失分在生产契约上全部不可复现**；唯一的契约拒绝（e2fd108ad9）对应的失分理由与盲评相同但机制不同（词面 vs 语义）。

## 3. 最重要 3 处可复现差异（精确 file:line）

### 差异 1：b294018f1c 空话计划结构合法通过（盲评 1,0,0,0）

- 复现：`probe-results.json` caseId=b294018f1c → `validate.accepted=true`，全部守卫空。
- 根因：`EvidenceTaskPlan`（contracts.py:113-116）只约束非空与长度；`validate_grounded_analysis`（contracts.py:272-441）无任何"具体性/可执行性"检查；`overclaim_flags` ability_claim（contracts.py:224-225）只认 `满足.{0,25}(?:岗位|要求)`，"材料符合岗位要求"（符合）漏网。
- 对照变体：同 case 控制组"材料满足岗位要求"被拒（probe-results.json variants）。**拒绝与否由"符合/满足"一词决定**——这正是"结构合法不冒充语义可靠"的直接证据。

### 差异 2：09fb4e82f3 共用账号矛盾——来源不可见，可见也不设防（盲评 0,2,0,1）

- 复现 A（不可见）：`probe-results.json` caseId=09fb4e82f3 → matcher evidence=[]，verdict=claimed_only。根因链：matcher.py:77 `find_evidence(files, "Python")` → Python 探测器仅 python_code（code_analyzer.py:161-167，需 `def ` + `.py`）且 DOCUMENT_RUBRICS 仅覆盖 活动策划/用户调研/内容运营（code_analyzer.py:375）→ group_report.md 零命中 → matcher.py:139-142 claimed_only。**"全组共用账号，未区分作者"从未进入 RequirementEvidenceContext**。
- 复现 B（可见仍不设防）：`probe2-source-visible.json` —— 注入 semantic_document_candidate（semantic_retrieval.py:169 真实形状）后 validate 仍 `accepted=true`。`_ATTRIBUTION`（task_boundaries.py:7-14）目标形状是"参考/小组材料 + 作为/当作/证明 + 本人贡献"，草稿"从版本历史筛出本人署名的提交"不匹配；task_boundaries.py:39 显式豁免"本人具名(的)提交记录"；且 `test_task_boundaries.py:98-107` **钉死**：共用账号来源 + "补交本人负责模块的贡献证明"未来计划必须返回 None。
- 含义：这不是某条守卫写漏，而是该矛盾在现有结构词汇里没有可靠形状——提取修复（让 markdown 入上下文）会改变全站 verdict/评级，不属于最小修复；契约侧可行的只有窄形状规则（§4-B）。

### 差异 3：e2fd108ad9 "源码存在=线上稳定"推断零 flag，拒绝纯属词面巧合（盲评 0,1,0,0）

- 复现：`probe-results.json` caseId=e2fd108ad9 → 拒绝串 "unsupported ability or execution claim"；逐文本分解显示唯一 flag 是步骤"将**代码**文件当作**已通过**运行测试的证据提交"（命中 contracts.py:229-230 execution_claim 的 `(?:测试|用例|代码|服务).{0,12}(?:全部通过|已通过|运行成功)`），而验收"源码存在即证明线上接口稳定运行"`overclaim_flags(..., planned_execution=True)`=**[]**。
- 变体 v1：步骤换成"整理 metrics.py 源码文件"后**整套接受**——即"已部署接口证明 + 源码存在即证明线上接口稳定运行"可通过生产契约。提示词防线（provider.py:278"未执行上传代码，不能断言测试通过、服务运行成功"）是模型侧软约束，validator 无对应结构检查。
- 含义：现有拒绝依赖草稿恰好写了"已通过"。修复方向见 §4-A。

## 4. 失分可处理性分类（四类点名问题逐一）

判定标准：可靠结构/来源规则必须满足——(a) 触发条件是来源或草稿的**显式词汇事实**，不是推断；(b) 正反例可枚举且既有钉死行为不碰撞；(c) 误触发可被一次修正（repair）消化。达不到的归"人工核对/模型引导"，不做关键词规则冒充语义证明。

### A. e2fd108ad9 已有源码 ≠ 部署/稳定运行 —— **可结构处理（推荐本轮实现）**

形状：交付物或验收主张部署/运行态结果（已部署|已上线|线上…稳定运行），而步骤不含任何产出运行记录的动作（运行|执行|部署|启动|请求|响应|调用|访问|日志）。触发即拒：`AI task plan asserts a deployment or runtime outcome without a runtime-record step`。这是对 `runtime_plan_without_implementation_step`（contracts.py:119-129）同族的形状补全，不判断"是否真的部署过"。

- 正例（必须拒）：e2fd108ad9 v1 形状（已部署接口证明 + 整理源码 + 源码存在即证明线上接口稳定运行）。
- 负例（必须放行）：37882b616f（步骤含"运行一次"）；853352704e 主形态（步骤"本地运行并保存…"；交付物无部署主张）；0f2a863462（交付物"执行记录"非部署主张）；f5c5e00efe；合法的部署取证计划（步骤含"调用接口并保存响应与时间戳"类）。
- 保守模式：拒绝 → 既有一次定向修正（evidence_workflow.py:574-599）→ 仍失败整体回退规则（evidence_workflow.py:662-712），降级行为零改动。
- 会影响的既有行为：contracts.py 校验序（建议挂在 contracts.py:364-367 现有计划守卫之后）；三个守卫测试文件必须保持绿：`test_task_boundaries.py`、`test_task_boundary_review_regressions.py`、`test_actionable_evidence_gaps.py:111`。已核对既有夹具无"已部署/稳定运行"措辞，无预期碰撞。

### B. 09fb4e82f3 共用账号不能筛出本人署名 —— **可结构处理，但必须窄到"从既有历史提取归属"形状（次选本轮实现）**

前置事实（§3 差异 2）：抽取层修复不在本轮范围（影响全站 verdict）；规则只能在候选行进入上下文时生效（fastembed 开启是生产常态路径）。设计约束：`test_task_boundaries.py:98-107` 钉死"未来补交贡献证明"必须放行，`test_task_boundaries.py:78-83` 钉死"列出本人提交的模块文件与对应提交记录"在"分工见附件"来源下放行。因此**规则只能匹配"计划从既有版本历史提取作者可区分条目"**（筛出.{0,8}本人署名|具名提交清单|提交记录包含作者…可定位为本人），不能笼统禁"具名/提交"。触发条件双门：① 个人来源片段显式断言归属不可能（共用账号|未区分作者|无法区分…提交者/作者）；② 计划文本含上述提取形状。拒拒信息给出可走路径（引用来源"附件"分工表并附组内书面确认，或按内容归属并声明局限）供修正轮使用。

- 正例（必须拒）：09fb4e82f3 草稿 × probe2 上下文。
- 负例（必须放行）：0f2a863462（来源无归属不可能断言）；`test_task_boundaries.py:102-107` 钉死形状（"补交…贡献证明并核对提交记录"无提取形状词）；`test_task_boundaries.py:78-83`（来源无断言）。
- 保守模式同 A（拒绝→修正→回退）。会影响的既有行为：`task_boundaries.task_boundary_error` 新增独立子句；须与 task_boundaries.py:39 的"本人具名提交记录"豁免并存（豁免针对"替代证明"判定，本规则针对"来源不可能性"，注释中写明分工）。
- 边界声明：语义替代路径（哪种贡献证明诚实可得）由修正轮模型与人工裁决，规则只挡"必然落空"的提取动作。

### C. 45c8ae3412 lru_cache 写失效机制未定义 —— **只能人工核对（不做规则）**

机制可行性（lru_cache 无法按需写入/逐键失效）要求理解库语义，属语义判断；且生产上下文只有 `def cache_get(key):` 一行，装饰器根本不可见（§2 表）。`test_task_boundaries.py:72-77` 已把"缓存读路径说明+补全写路径计划"钉死为合法形状——现有设计有意接受该形状。可做：仅提示词引导（provider.py task_plan 段加一句"计划涉及缓存失效时须写明失效机制与期望观测"），无 validator 强制；残余风险由 neededSupplements 人工核对承担。**不建议**为它造关键词规则。

### D. 853352704e Redis 键设计遗漏 —— **只能人工核对（不做规则）**

"交付物是否覆盖需求标题全部要素"是需求覆盖语义判断；"标题词 ⊆ 计划文本"的词面检查正是卡面禁止的冒充（且中文标题分词脆弱）。生产已有部分正确行为：显式"未实现"来源 + 纯运行计划会被拒（变体 v1 实证，contracts.py:143-175），评级 ceiling=1 正确压级。可做：提示词引导（建议对 gap/claimed_only 项要求计划显式对应要求标题各要素或说明不覆盖理由），同样无强制。

### 其余失分模式

- b294018f1c 笼统空话：语义判断，不做规则。已核对**不**建议把"符合"并入 ability_claim——planned_execution 的 future_condition 豁免只覆盖 execution_claim（contracts.py:256-266），扩 ability_claim 会在合法计划语句（"确保内容符合岗位要求"类）上误触发。
- 盲评与生产的系统性可见性差（.py 只入 def 行、无 rubric 技能的 markdown 行级候选）：是抽取设计（行级、低强度、不改判定）的既定行为，本轮不动；作为边界写入接力。

## 5. 下一有界实现提案（汇总）

- **允许文件**：`backend/app/agents/contracts.py`（规则 A；如 Codex 批准 B，则 `backend/app/tools/task_boundaries.py`）；对应测试 `backend/app/tests/test_task_boundaries.py`、`backend/app/tests/test_task_boundary_review_regressions.py`、`backend/app/tests/test_actionable_evidence_gaps.py`（新增正反例用例，不改既有断言）；可选提示词引导 `backend/app/agents/provider.py`（仅 C/D 引导句，不强求）。
- **正反例**：§4-A/B 已列，全部有探针实测基线（probe-results.json / probe2-source-visible.json 可作回归对照）。
- **保守拒绝/修正/fallback**：两规则均为"新增拒绝"→ 既有一次修正 → 整体回退，零降级改动；消息文本内嵌可执行的人工替代路径。
- **会影响的既有行为**：validate_grounded_analysis 校验序追加两处守卫（先 A 后 B）；三个守卫测试文件必须保持绿；`test_task_boundaries.py:98-107`、`:78-83`、`:72-77`、`:56-66` 为关键回归锚点；无 schema/持久化/API 变更；`task_plan_redundant_source_request` 读时复检路径（function_coverage.py:167）不受影响（新规则不在其中——如需读时复检同族扩展，另立批次）。
- **明确不做**：抽取层可见性变更；"符合"并入 overclaim；lru_cache/键设计关键词规则；对 8 例分数或黄金标签的任何回写。

## 6. 边界与不冒充声明

- 本审查全部结论针对**作者合成草稿**（输入包 kind=authored-synthetic-drafts-not-website-model-output）与生产契约函数的映射行为；盲评分数 humanReview=false，不代表网站真实 AI 建议质量，本审查亦未运行任何真实模型。
- "生产契约接受"是结构事实，不是质量结论；"拒绝"只在词面层面成立（§3 差异 3），不构成语义否证。
- 探针映射偏差（§1.3）已如实列出；09fb4e82f3 的 verdict 在真实解析下可能是 gap 而非 claimed_only，该偏差不影响计划守卫结论。
- 语义可靠性的判定（哪些失分是"真"失分）仍归 Codex 裁决与人工核对；本审查只证明"生产结构层看不见/挡不住"的可复现事实。

## 7. 自审清单

- [x] 唯一写入面：本目录 + `backend/.tmp-plan-audit-30/`（自有无数据 scratch，仅探针脚本与其输出）。未改任何源码/测试/标签/评分；无 Git 操作；无 provider/联网/DB/服务/浏览器/安装。
- [x] 未重复已签收检查（不重跑全量测试、不复述盲评分数作结论）；所有差异均给当前生产 file:line 与可复现探针输出。
- [x] 未把独立评分当生产输出；未把结构接受冒充语义可靠；卡面四个点名问题逐一给出分类与理由。
- [x] 探针两次运行 exit=0、stderr 空、命令与源 hash 存档（probe-commands.out / manifest.json）；探针源码存档于本目录，可执行副本路径已在 §1.2 注明（evidence 副本因相对路径不可直接运行）。
- [x] 修复提案限定允许文件、正反例、保守模式与既有行为影响，并显式列出"明确不做"清单。

## 8. 交棒 Codex（复核点）

1. 裁决 §4 分类：A/B 是否批准进入有界实现；C/D 是否按"人工核对+可选提示词"归档。
2. 复核差异 2 的两层证据（probe1 evidence=[] / probe2 可见仍接受）与 `test_task_boundaries.py:98-107` 的设计意图是否如本审计解读（"未来补交允许"是否也覆盖"从历史提取署名"——我们判定不覆盖，需终审）。
3. 复核 §3 差异 3 的"词面巧合"定性及规则 A 的负例面（有无生产合法计划会因"已部署"措辞被误拒）。
4. 决定 B 规则的触发词表与豁免并存注释；批准后按 §5 允许文件实施，实施时以 probe-results.json 为回归对照基线。
