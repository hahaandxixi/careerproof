# 2026-10-19 Agent 工具边界补强与评分证据矩阵

范围：核对 Agent、Function Calling、MCP 接线；新增一个有界回归并修复一个工具边界缺陷。没有真实模型请求、没有改历史报告/评分协议/数据库。三文件于 2026-10-19 单独提交；受管后端在提交后重启以加载相同源码。

结论先行：

- 原分析中“未实现 MCP”“只有一个受控工具”已被当前源码和当前验证推翻；“没有 token 流式输出”成立，但不等于没有过程反馈。
- “不是通用自主 Agent”“只有受控的一轮一个工具”“当前 v29 没有真实模型工具规划证据”“当前三例人工复核 0”仍然成立。
- 本轮没有把历史 v23 的真实报告自动算成当前候选版通过；历史证据和当前证据分列。
- 不把测试数、技术栈数量或历史截图折算成评委分数；本页不提供子项分数或总分预测。

## 一、事实纠正

参照的旧判断在 [历史验收汇编](../历史验收汇编.md) 的 2026-09 提交对照（约 4143、4147、4156 行）。

| 旧判断 | 当前核对结果 | 依据 |
| --- | --- | --- |
| “未实现 MCP” | **推翻。** 已有 FastMCP stdio 服务、三个只读工具、十分钟专用令牌、报告范围、撤销、40 次上限和独立审计；当前依赖下官方 SDK stdio 联验通过。 | `backend/app/mcp_server.py`、`backend/app/services/mcp_tools.py`、`backend/app/api/v1/mcp_tools.py`、`jianli/src/components/McpAccessPanel.tsx`；本轮 `mcp-stdio-current.raw.out` |
| “当前只有一个受控工具” | **部分推翻。** 网站内部有两个工具：`retrieve_more_evidence` 与 `get_previous_report_context`；MCP 另有三个只读工具。仍不是通用工具生态，内部每轮只能选一个工具。 | `backend/app/agents/provider.py:791-949`、`backend/app/agents/evidence_workflow.py:384-551` |
| “单工具、单步工作流” | **过时。** 最多两轮工具规划，可先查历史再补检索，也可停止；工具结果会更新上下文并进入最终分析。仍不是可自由规划、可执行任意工具的 Agent。 | `evidence_workflow.py` 的循环、预算预留、`tool_calls` 记录；`ReportDetail.tsx:25-32,68` |
| “没有真实 AI 调用” | **不成立。** 2026-10-18 已有当前提示词 v29 的 3 次真实 DeepSeek 调用，结构/引用校验 3/3，但人工语义 0。更早的 v23 有真实完整报告与真实工具调用；不能把两者混成当前候选版。 | [task70 review](../20261017-task70-semantic-review-packet/review.md)；历史 v23 记录 |
| “没有 token 流式输出” | **成立，但不等于没有过程反馈。** 任务页使用真实 SSE `task.progress/completed/failed`，有阶段、百分比、连接状态、降级标识和轮询回退；报告页展开受控工具记录。 | `jianli/src/components/TaskView.tsx:45-107,157-190`、`ReportDetail.tsx:68` |
| “没有 Agent” | **不准确。** 是有边界的服务端受控工具工作流，不是通用自主 Agent；应以“受控 Agent 工作流”表述，不能宣传成通用 Agent。 | 同上；另见 `docs/guides/工具与接入.md` |

## 二、评分证据矩阵

证据等级：A 实现与接线已确认；B 离线/合成测试通过；C 真实协议或真实模型链路通过；D 正常网站真实页面通过；E 独立人员使用或语义验收。等级不机械递进，范围写在格内。

| 子项（权重） | 实际能力与入口 | 当前证据与等级 | 缺口 / 本轮判断 |
| --- | --- | --- | --- |
| 大模型集成 8% | DeepSeek 官方 `deepseek-flash`；OpenAI 兼容 JSON、低温度、引用/过度结论校验、一次定向修正、预算与规则降级。`provider.py`、`analysis.py:804` | A：接线确认。C：v29 三例合成输入真实调用 9496/1315 tokens，结构/引用 3/3；C（历史）：v23 真实完整报告。D/E：当前 v29 无正常站真实报告、人工 0 | 当前提示词缺独立语义复核；三例不是网站链路。下一项应做真实模型语义复核，不新增供应商 |
| Agent/工作流 8% | 最多两轮规划；模型可选补检索、查本人同岗历史或停止；服务端白名单、参数/作用域/次数/预算；结果回填后继续分析；拒绝/停止/降级入 `modelToolCalls`；报告页展示。`evidence_workflow.py`、`ReportDetail.tsx` | A：接线确认。B：本轮 93 项相关回归通过（含新增边界）。C/D（历史）：v19/v23 真实完整报告、浏览器键盘链、R1-E3。当前 v29 无真实工具规划 C | 真实模型可能不调用工具，合理停止也是有效行为；不能用离线替身冒充。当前缺“当前版本一次真实规划→工具结果→结论变化”的 C/D |
| RAG 6% | 规则候选、词法/哈希、本地 ONNX 语义候选、冻结材料定向补检索；引用白名单和行号来源。`app/tools/`、`evidence_workflow.py` | A/B：64 例冻结合成对照、4 个语义小例、定向补检索专项。C：历史报告引用可定位。D：报告来源展开。独立标注/语义增益未验 | 缺“补检索 vs 不补检索”的当前小样本对照（固定材料/岗位/提示/模型/预算）；不能由引用合法率推出语义正确或统计显著 |
| 多模态 5% | 本地 RapidOCR；DeepSeek 单图 `image_url` 观察，独立原图外发同意、归一化区域、待核验项、不进入评级。`vision_provider.py`、`visual_evidence.py`、`VisualEvidencePanel.tsx` | A：接线确认。C（历史）：两次真实合成视觉回答、浏览器键盘生成/复核/刷新、390px。E：区域独立标注/人工语义 0 | PDF/DOCX/ZIP 解析不算三种模态；不新增语音/视频。当前缺真实人员核对区域与“图片不能证明什么”的语义验收 |
| AI 安全与可控 4% | 外发同意、直接标识脱敏、凭据过滤、工具白名单、引用/过度结论校验、预算硬停、规则降级、审计；本轮补工具越界拒绝 | A/B：实现与离线回归。C：真实输出结构/引用通过。D：历史页面降级/授权链。E：0 | 不能把结构校验等同语义正确；当前三例人工复核 0。工具调用异常此前可导致整份 AI 报告降级，本轮已修一个边界 |
| MCP/工具集成 4% | FastMCP stdio 三工具：检索已授权报告片段、摘要、比较；专用短令牌、撤销、40 次、账号状态复查、审计；不是登录令牌。`mcp_server.py`、`mcp_tools.py`、`McpAccessPanel.tsx` | A：接线确认。C：**本轮**官方 SDK stdio → 本机 HTTP → 临时 SQLite，授权读取/越权拒绝/撤销后拒绝/审计/脱敏 1 项通过，2.57s。D（历史）：报告页键盘授权/撤销。商业客户端/E 未验 | 不是公开远程 OAuth，也不是商业客户端自主规划；外部客户端仍可能把结果发给其模型商。旧“没有 MCP”判断应删除 |
| 创新性·选题 10% | “简历声明—项目证据—岗位要求—人工复核—补证变化”的证据链；反过度结论。`README.md`、报告/成长页 | A/D：链路实现并有真实页面证据；B：多轮离线评测。无竞品系统对照、无独立用户研究 | 不能自称首创或优于其他作品；需要用一页问题/替代方案/差异证据说明“为什么不是普通简历评分” |
| 创新性·技术方案 8% | 受控工具工作流、版本/哈希固定、引用回原文、规则上限与 AI 初评分层 | A/B/C（历史）。当前版本 C 仅 3 例单次分析，不含工具 | 方案的“证据约束”有实现，但缺当前真实 Agent trace 和独立语义；不要用技术名词替代 |
| 创新性·交互模式 7% | 报告动作层、工具记录展开、缺口任务、企业固定报告对照、MCP 授权面板 | D（历史/10-19 局部页面）；A | 缺未参与实现者的首次使用观察；复杂概念是否可理解未验 |
| 前端工程·代码质量 4% | Next.js/React/TypeScript、集中 API 客户端、真实组件测试、类型/构建/lint。`jianli/src` | A：结构确认。B/D：10/18 前端 335 项；10/19 目标 49 项、type/lint/build 通过；10/19 1280/390 实际页面 | 本轮未改前端，不重跑全量；测试数量不等于代码质量。仍有大型内联 JSX 组件，未做覆盖率/复杂度量化 |
| 前端工程·组件架构 3% | 页面/会话/展示组件分层，异步票据与卸载保护，统一状态文案 | A；B（专项测试）。无正式架构评审或依赖图 | 可补一页关键组件/数据流，不应为评分重构 |
| 前端工程·性能 3% | 有生产构建；本轮未测首屏、长报告、移动端延迟 | **未核实** | 不能凭一次 Lighthouse 给全站定性；先记录生产构建、页面、视口、缓存、冷/热条件，再决定是否改 |
| 实用性·真实场景 5% | 学生上传→解析→选岗→报告→补证→投递；企业固定报告/回复；撤回/重投；通知 | A/D：10/14—10/19 多条真实合成页面链；E：独立首次用户 0 | 真实个人材料未用于外发；缺未参与实现者的完整首次走查 |
| 实用性·方案有效性 5% | 报告给出可定位来源、缺口任务、版本变化；企业只读固定快照 | A/B/D；有真实合成链路。没有“用户照建议补证后获得面试/效率提升”的结果研究 | 只能证明流程可完成和证据可定位，不能证明就业结果；不要把流程成功写成方案有效 |
| 用户体验·UI/响应式 4% | 原版 slate/indigo，1280/390 页面；关键页历史 320px/键盘 | D：10/19 真实 1280/390；历史 320px。当前 200% 缩放、reduced-motion 实偏好未验 | 不整站换肤；缺真实系统辅助偏好验收 |
| 用户体验·前端交互 3% | 表单防重、失败重试、SSE/轮询、连接状态、通知/投递恢复 | D（历史/10-19 局部）；B 组件测试 | 全鼠标新材料上传、完整移动端流程仍有历史缺口；不能由单页截图替代 |
| 用户体验·AI 交互 3% | 阶段 SSE、模型规划/停止/拒绝/降级记录、引用跳转、报告内工具 trace、MCP 授权 | D（历史），A；当前 v29 无真实站点 AI 报告 | 不要求 token 流；需要让用户看懂“模型做了什么/没做什么”，当前历史报告可展开，但当前候选未验 |
| 社会价值 5% | 面向学生求职证据不足与夸大表述；强调可解释、可撤回、不推断录用 | A/文档；D 合成链；无用户调研、无影响指标 | 社会价值主张有产品落点，但缺真实用户证据；不能仅凭愿景打高分 |
| 商业潜力 5% | 无定价、客户、成本、付费意愿或市场规模实测 | **未核实** | 不编造商业模式数据；如时间不足，保留为答辩待答问题而非新增模块 |

## 三、本轮补强

### 问题

当启用“查询本人同岗位历史”时，规划器会看到全部有证据的要求；某个要求已经达到 3 条引用后，模型仍可能再次选择 `retrieve_more_evidence`。旧实现让这个本应被拒绝的工具步骤抛出 `ValueError`，被外层当成工作流故障，整份 AI 报告降级为规则报告（`fallback_used=true`，`failure_stage=tool_execution`），且没有留下这一轮拒绝事件。

### 评分关联

- Agent/工作流 8%：工具调用的继续/停止/拒绝语义属于“规划、工具调用和自主决策”的可靠性，不是新增功能。
- AI 安全与可控 4%：模型输出不能突破服务端引用上限；越界应只拒绝该工具步骤并保留已验证证据。
- 不影响大模型选型、评分公式、历史报告或数据库。

### 最小工作

1. `backend/app/agents/evidence_workflow.py`
   - 在工具执行前统一核对目标要求是否仍在可补检索范围；目标缺失或已有 3 条引用时，记录 `status=rejected`、`reason=ineligible_retrieval_scope`，停止本轮规划并继续最终分析。
   - `execute_retrieval_tool` 的成功/无结果事件增加显式 `status=completed` / `no_result`，使记录能区分“计划、执行、成功、无结果、拒绝、降级”。
2. `backend/app/tests/test_report_history.py`
   - 新增回归：两轮规划、第二轮模型对已满 3 条的要求再次请求补检索；修复前整份报告降级，修复后保留 `R1-E3` 的分析并记录拒绝。
3. `backend/app/tests/test_ai_evidence_workflow.py`
   - 锁定成功状态 `completed`；新增无新候选时 `no_result` 与 `resultCount=0`。

### 验收方法

- 红：新增回归首次运行失败，实际 `fallback_used=True`、`fallback_reason=invalid_output_or_config`、`failure_stage=tool_execution`、无第二轮拒绝事件。
- 绿：同一用例通过，工具事件为 `completed`（第 1 轮）→ `rejected/ineligible_retrieval_scope`（第 2 轮），最终分析保留且引用 `R1-E3`，无降级。
- 相关 5 个测试文件 93 通过；MCP 官方 SDK stdio 1 通过；Ruff 通过。

### 影响范围

- 只影响 `analysis_metadata.modelToolCalls` 及报告页已有工具记录的读取；旧报告没有新 `status` 时仍按原 `resultCount` 显示，不回写。
- 不新增请求、不改变预算上限、不改变工具白名单、不改变评分/等级；不保证真实模型一定调用工具。
- 不估算评委分增量：没有真实触发率、当前版本语义评分或评委校准数据。可以确定的是，这一边界从“整份 AI 报告降级”变为“只拒绝越界工具步骤”，属于 8% Agent 与 4% 安全可控子项的证据补强，而不是新增得分项。

## 四、验证记录

- 提交前 HEAD：`24677662cb51224da205b054a067cffe07703bad`（main）。
- 环境：Windows；`backend/.venv-dependency23`；Python 3.12.14；pytest 使用仓库内 `backend/.tmp` 作为 `--basetemp`，避开系统 TEMP 权限错误。
- 依赖现场：`mcp 1.30.0`、`sse-starlette 3.0.3`、`httpx 0.28.1`、`pydantic 2.11.7`。
- Agent 相关：
  `python -m pytest app/tests/test_report_history.py app/tests/test_ai_evidence_workflow.py app/tests/test_zhipu_provider.py app/tests/test_directed_retrieval.py app/tests/test_report_input_budget.py -q --no-header -p no:cacheprovider --basetemp=.tmp/agent-boundary-evidence`
  → **93 passed, 5 warnings, 4.72s**（最终输出 `agent-related-tests-final.raw.out`）。
- MCP 当前协议：
  `python -m pytest app/tests/test_mcp_stdio_integration.py -q --no-header -p no:cacheprovider --basetemp=.tmp/mcp-stdio-evidence`
  → **1 passed, 5 warnings, 2.57s**（`mcp-stdio-current.raw.out`，stderr 单列 `mcp-stdio-current.raw.err`；临时 SQLite、本机 loopback HTTP、官方 SDK stdio；不证明商业客户端或 PostgreSQL 并发）。
- `python -m ruff check app/agents/evidence_workflow.py app/tests/test_report_history.py app/tests/test_ai_evidence_workflow.py`
  → **All checks passed**（`ruff-final.raw.out`）。未把 `ruff format --check` 写成通过：被改文件在 HEAD 已有整文件重排差异，本轮不做无关全文件格式化。
- 源码加载核对：后端进程 21:17:02 启动，三文件最后修改为 12:15—12:17；无 reload，运行进程在启动时已导入该工作树源码。三文件提交后用受管启停重启，后端进程启动时间晚于提交，确保运行源码与验收记录对齐。
- 正常站：`http://127.0.0.1:3000` 返回 200；`http://127.0.0.1:8000/api/v1/health` 返回 200。**本轮未生成新的 AI 报告，因此不能声称 `completed/rejected` 新状态已在真实报告页显示。**

## 五、已验证 / 未验证边界

已验证：

- 当前 worktree 的 Agent 工作流在合成 provider 响应下，能执行“补检索→结果进入上下文→最终分析引用新证据”的闭环，并在越界时只拒绝工具步骤。
- 当前依赖下官方 MCP SDK stdio 能完成三工具发现、授权范围读取、越权拒绝、撤销后拒绝、审计与脱敏；测试使用临时 SQLite 和合成报告。
- 既有历史真实模型报告、真实 MCP SDK 联验、正常页面链仍可作为历史证据，但**不能自动等同于当前候选版本**。

未验证：

- 当前 v29 提示词下真实 DeepSeek 是否选择工具、选择后结论是否改变（无新授权，本轮未发真实请求）。
- 本轮 `status` 是否在正常站真实报告页显示（未生成新 AI 报告；页面级未验）。
- PostgreSQL 下的 MCP 并发/锁语义（本轮只跑 SQLite 协议链；历史 PG 证据另列）。
- 商业 MCP 客户端、外部客户端界面、独立人工语义/区域标注、首次独立用户、性能基准、完整后端全量、前端全量、候选冻结。
- 本轮只显式提交三文件，不推送；`docs/当前接力.md`、`docs/guides/使用与启动.md`、`jianli/src/components/JobDetailView.tsx` 及角色一致性证据的既有改动不属于本轮，未覆盖。

## 六、接下来三项

1. **当前版本真实 Agent trace（最高收益，需 Codex/用户授权）**
   - 收益：把 Agent 8% 与 AI 可控 4% 从 A/B + 历史 C 提升到当前版本 C；能直接回答“原先缺什么→选了什么工具→返回什么→结论是否变化”。
   - 风险：真实请求可能不调用工具（合理停止也是结果）；必须固定合成输入、提示版本、模型、最多物理请求数、输入/输出上限、价格和停止规则；旧三例授权不能扩展。
   - 人工依赖：Codex 定授权包与预算，用户确认。
2. **独立人工语义复核（现有三例 + 一条当前 Agent trace）**
   - 收益：E 级证据直接补 Agent、LLM、AI 安全、创新性；不需要新增模型调用。
   - 风险：评审者需先独立阅读材料，不能由实现者代签；只说明这些案例，不宣称统计显著。
   - 人工依赖：未参与实现的同学/同事。
3. **运行源码对齐（已完成）与页面新状态审计（未完成）**
   - 已完成：三文件提交后按受管流程停止/重启，后端新进程晚于提交，运行源码与验收记录对齐；3000/8000 健康 200。
   - 未完成：没有新的真实 AI 报告，`completed/rejected` 新状态未在真实报告页显示；旧报告/规则报告只做健康检查，不伪造新事件。

## 七、交给 Codex 的集成/终验

1. 复核三文件 diff；确认不触碰历史报告、评分协议、授权/固定快照。
2. 用干净环境复跑本页命令；三文件与证据已显式提交，其他未提交改动未暂存。
3. 核对提交后受管重启生成的清单、后端新 PID 和 3000/8000 健康；不把重启等同真实 AI 页面验收。
4. 当前版本真实 Agent 验证：先按授权格式固定合成输入、提示词版本、模型、物理请求上限、输入/输出上限、价格依据和停止规则；旧三例授权不扩展。
5. 把本页矩阵并入正式交付材料时，保留证据等级、未验证项和不评分说明；不要写成“当前候选版已通过全部 AI/MCP/人工验收”。

## 八、文件与证据

- 源码：`backend/app/agents/evidence_workflow.py`
- 回归：`backend/app/tests/test_report_history.py`、`backend/app/tests/test_ai_evidence_workflow.py`
- 最终输出：`agent-related-tests-final.raw.out`、`agent-related-tests-final.exit`、`ruff-final.raw.out`
- 历史输出保留：`agent-related-tests.raw.out`、`ruff.raw.out`、`mcp-stdio-current.raw.out`、`mcp-stdio-current.raw.err`
- 修复前终端转录：`red-before-fix-transcript.txt`（原始 pty 未保存，已如实标注）
- 版本与哈希：`git-baseline.txt`、`source-hashes.txt`
- 退出码：`exit-codes.txt`
