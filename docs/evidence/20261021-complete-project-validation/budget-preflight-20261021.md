# 完整五项报告输入预算预检

状态：**仅离线预检，未授权、未发送真实请求、未生成新的 AI 报告。**

## 1. 源码与旧授权状态

当前 HEAD：`94701564943066af482e811a1780b4cdec740e35`

当前源码指纹：

| 文件 | SHA256 |
| --- | --- |
| `backend/app/tools/code_analyzer.py` | `a353c2961474f04caf0cbf9aeb2c20f4e485f5ff3df9ab0f551f9264c8f57186` |
| `backend/app/tools/matcher.py` | `8ca77bd966b79822fea1882ca5e8e164fd0aa6ca6e8b5f34992f44b6c6b3647d` |
| `backend/app/agents/provider.py` | `700f2544e5c06b3883769caac6e2eaaefa35cc710ec64e78730eb285ac962297` |
| `backend/app/agents/evidence_workflow.py` | `56ca89ed61ed19a588e29db9eb57a6e8c05738b7ce45d71dfc11cfeed65012ea` |
| `backend/app/agents/contracts.py` | `8fb59d9ebda61bdedaf29cd01b7196ce1413262878bd88583934f4e588641602` |

**旧三例授权包不能用于本轮完整五项报告：**

- `agent-live-preflight-20261020.json` 的包 SHA256 为 `930bc0001e76965dc4c8fc1dd4573a7cd3edd6bd8fca45b108c20926fef431da`；
- 其中 `matcher.py`、`code_analyzer.py` 哈希已与 `9470156` 当前源码不一致；
- 用当前 `check_agent_packet` 检查旧包，返回 `SmokeStopped: Agent reviewed source changed`；
- 该包只覆盖三个合成单例，不覆盖完整五项；旧授权额度不能扩展。

完整项目 `agent-preflight/result.json` 也记录 `legacyAuthorizationApplicable: false`。当前**没有**完整五项真实 Agent 授权。

## 2. 有效上限与测量口径

- 隔离环境的报告输入上限：**12,000**（`ai_per_report_input_token_limit` 默认/隔离配置）。
- 输出上限：**4,000**（`ai_per_report_output_token_limit`）。
- 正常工程 `.env` 当前写有 `AI_PER_REPORT_INPUT_TOKEN_LIMIT=40000`，**不**作为本预检依据，也不建议通过调大上限解决。
- 所有数字均为现有 `conservative_input_token_estimate` 的 JSON 字符上界，不是供应商账单 token；不代表实际计费。
- 使用 `516cc695-5044-481f-ab9b-5ffa5e59f1a5` 的完整五项规则证据和当前 provider 消息构建器；含 Python 第 3 条 `cancel`，不含真实模型响应。

## 3. 完整五项单请求测量

| 组成 | 字符/预算 | 说明 |
| --- | --- | --- |
| 系统提示 | 5,339 | 含证据边界、引用、失败停止和输出约束 |
| 引用片段（11 条，含 cancel） | 约 11,208 | `service.py` 报名/取消/事务、SQL、测试等 |
| 判据 `rating_rubric`（5 项重复） | 1,234 | 每项重复同一组判据 |
| `function_source_coverage` + `file_source_coverage` | 2,588 | 五项重复的结构化覆盖信息 |
| 要求/ID/verdict/citation policy 等余量 | 约 3,631 | 用户消息其他字段与 JSON 包裹 |
| **分析消息总计** | **约 24,000** | 超过 12,000，单请求不可执行 |
| 工具 Schema | 319 | 仅规划请求；不计入分析消息 |
| 历史上下文 | 0 | 本方案不发送历史 |

阶段：

| 阶段 | 估算 | 说明 |
| --- | --- | --- |
| 规划请求消息 | 11,439 | 五项目标 + 工具选择；加工具 Schema 后约 11,758 |
| 初始分析请求 | 约 24,000 | 单请求超过 12,000 |
| 补入 SQL 事务后分析 | 约 24,766 | 仍超过 12,000 |
| 完整五项修复请求 | 约 26,678 | 带 rejectedOutput/feedback，超过 12,000 |

**结论：不能用“Python 单项 11,434 < 12,000”证明完整五项可执行。** 完整五项单请求和完整修复请求都超限。

## 4. 最小压缩与分项方案

### 压缩

只去掉每项重复的 `function_source_coverage`/`file_source_coverage` 结构化载荷，保留：

- 全部 11 条引用片段和 citation ID；
- 岗位要求、verdict、claim；
- 判据 `rating_rubric`；
- 证据来源、行区间和上下文完整性说明；
- 失败停止、引用映射和输出约束。

不缩短关键实现原文，不删反例或限制条件。压缩后五项仍有约 **21,412**，单请求仍超限，因此必须分项。

### 三个分析批次

| 批次 | 要求 | 压缩后输入上界 |
| --- | --- | --- |
| A | FastAPI + SQL | **11,793** |
| B | Python（含事务/报名/取消 3 条） | **10,491** |
| C | pytest + Redis | **9,562** |

所有批次均低于 12,000。Python 的 `cancel` 不再被 `max_evidence=2` 截掉，因此 B 批次固定保留 3 条 Python 业务证据。

### 请求与汇总

- **规划**：1 次；规划消息 11,439，带工具 Schema 约 11,758。本方案不执行工具补检索；若后续需要工具结果，必须另算 A 批次增量。
- **分析**：3 次，分别对应 A/B/C；每次输入上限 12,000。
- **修复**：本方案**不预留完整五项修复**；完整修复约 26,678，超过 12,000。任一分析未通过结构/引用/grounding 校验即硬停止，不重发、不把 fallback 写成完成。
- **物理请求上限**：4 次（1 规划 + 3 分析），不含传输重试；若执行器有自动重试，必须计入 4 次总量。
- **汇总方式**：按 `requirement_id` 确定性合并 3 份 items；恰好 5 项、无缺失/重复/越界 ID；引用 ID 映射按各批次保留；不额外调用模型生成汇总。任一批次缺项即整体停止。
- **输出预算**：规划最多 200，3 个分析各 1,200，合计 3,800 ≤ 4,000；不把 4,000 当作每个请求都可用的额度。

## 5. 边界与后续

- 当前生产工作流仍是一次分析五个 requirement；三批次分析和确定性合并**尚未实现**，本文件只是离线调用方案，不是可执行授权。
- 本方案不修改 provider、预算守卫或评分公式；不新增真实请求。
- 旧三例授权不扩展；完整五项需要新的明确授权。
- 需要先补：分组分析/合并实现、每批次的失败停止与引用校验、取消 `max_evidence=2` 对 Python 的截断（B 批次固定 3 条）。
- 未验证：真实模型对分项输出的语义一致性、跨批次解释合并、页面展示、真人评审。
- 现有证据：`python-selection-fix/report-after.json` 是规则报告，不是 AI 结果；本预检不据它宣称 AI 完成。

## 6. 复现材料

- 本文件
- `budget-preflight-20261021.json`
- 现有完整五项规则报告：`python-selection-fix/report-after.json`
- 旧预检：`agent-preflight/result.json`（legacyAuthorizationApplicable=false）
- 旧授权包：`../20261019-agent-boundary/agent-live-preflight-20261020.json`（哈希已失配，禁止使用）

本结果是 AI 辅助离线预检，不是真人评审、真实模型验收或独立用户验收。
