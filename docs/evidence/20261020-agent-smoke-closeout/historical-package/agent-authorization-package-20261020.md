# 当前版本 Agent 真实调用授权包

状态：**待审批，未执行。** 本文件不是授权，不构成对外发送许可。当前外部请求为 0。

## 一、目的

验证当前 `run_evidence_workflow` 的真实模型链路是否能完成：

1. 在固定合成材料上规划一次补检索或停止；
2. 让白名单工具结果进入后续分析，或在无新候选时由程序跳过规划；
3. 让历史上下文只作参考，不成为当前评级引用；
4. 记录实际物理请求、阶段、动态请求哈希、工具执行和最终输出。

不以“模型必须调用工具”为成功标准；合理停止、程序跳过和规则降级分别记录。

## 二、固定输入

输入包：[agent-live-preflight-20261020.json](agent-live-preflight-20261020.json)

- 包 SHA256：`1ac3278bcd29454ae15f28830c506a04870f8c7d58575868d06fbd3da6940c86`
- 批 ID：`agent-live-20261020-three-cases`
- 所有材料、证据片段、历史均为合成；不读取真实简历、正常库报告、用户上传或凭据。

| 案例 | 位置 | 证据数 | 历史 | 案例 JSON SHA256 | 设计观察 |
| --- | --- | --- | --- | --- | --- |
| AG-01 | `cases[0]` | 3（上下文展示 2，候选 1） | 无 | `e4efb2d5b4aee561721c6928d40459e76d7e982bfad42ea2413256dfe6c5ab87` | 是否选择补检索；新增引用是否进入最终分析 |
| AG-02 | `cases[1]` | 2（无新候选） | 无 | `67f1f1f46e41380e70e7089e913baceb6aa6cdd571276b668f9c6b4e50ef1d10` | 程序是否跳过规划；不把跳过写成模型停止 |
| AG-03 | `cases[2]` | 2 | 固定上一份合成报告 | `401cd02fa0cdb97263f7ed6e5871443d0df1cf541f22de2c0c3494ffe07a0046` | 是否查询历史；历史是否仅作参考 |

AG-01 的第三片段属于固定 `project/order.py` 候选，不在初始两条引用中。AG-02 没有第三候选，因此正常路径应是程序跳过规划。AG-03 的历史 `previousReportId` 固定，不能被最终引用或提升评级。

## 三、源码、提示词、模型与工具

- 基准 HEAD：`b756d3231f317078948f2da118e03e79e5aae4aa`
- 本轮执行器改动（工作树，待 Codex 集成/提交）：
  - `backend/evals/bounded_evidence_smoke.py`
    SHA256 `735cfd12ed83668efeb437692c0f05dd6fe52a50ae9959c4fda31e4f55efa484`
  - `backend/app/tests/test_agent_evidence_smoke.py`
    SHA256 `a5e639ce461365aba694bc2b912fb8402db9c8d3f93329c4641a9e6efe0edb4e`
  - `backend/app/tests/test_bounded_evidence_smoke.py`
    SHA256 `47cd6a9b2bc1b837bb28e27b61f4e1583b73c582c9f8be3027cace44c2ffd521`
- 模型：`deepseek-flash`
- 提示词：`evidence-trust-v29-implementation-first-plan`
- thinking：disabled
- `provider.py` SHA256 `700f2544e5c06b3883769caac6e2eaaefa35cc710ec64e78730eb285ac962297`
- `evidence_workflow.py` SHA256 `8e7538b2e66317ba61dfbd8ec6cfce7b2aa054c8b4bf07d6b164bcfb529aca4e`
- 接入方式：`run_evidence_workflow(..., provider_override=...)`；默认参数不改变生产调用路径。执行器把受约束 provider 传入真实工作流，不依赖两个模块工厂返回同一对象。
- 离线回归：**38 passed**（含修复前红测、provider 注入、硬停止、模型停止/程序跳过、来源篡改、历史身份变化、旧包拒绝）；红测原始失败见 `agent-preflight-red-before-fix.raw.out`。
- `contracts.py` SHA256 `cd6d6eb6466b78ac2b50d6880d324c42f61adf337416b53126d540222f2fe280`
- 工具：只允许 `retrieve_more_evidence` 与 `get_previous_report_context`；`tool_choice=auto`；最多 2 轮规划；每轮最多一个工具。
- 工具执行只读固定合成数据，不访问网络/文件系统/数据库。

**源码发生变化时包检查会拒绝执行。** 审批前应先由 Codex 提交上述精确源码，或确认工作树哈希与本包一致。

## 四、请求与预算

| 项目 | 数值 | 作用范围 |
| --- | --- | --- |
| 每例物理请求上限 | 4 | 每例，含规划 1、规划 2、最终分析、一次修正；含任何重试 |
| 整批物理请求上限 | 12 | 3 例总计，含首次和重试 |
| 输入保守上界 | 20,000 | **每次 HTTP 请求**；程序 JSON/字符上界，不是供应商 token 账单 |
| 输出上限 | 1,200 | **每次 HTTP 请求**的 `max_tokens` |
| 费用硬上限 | 2 元人民币 | **整批**，不是每例 |

执行器设置 `provider._max_attempts=1`，因此本轮计划不使用自动重试；若传输层仍发生重试，仍会经过同一 `before_send` 并按每例/整批上限消耗。

每请求预留按旧的 2 元/百万输入、8 元/百万输出计算的保守上限为 `0.0496` 元；12 次最多 `0.5952` 元。**这是旧价格场景，不是当前报价，也不是账单。**

## 五、价格状态

- 当前状态：**待核验**。
- 2026-10-18 的 `deepseek-prices-20261018.json` 只作历史参考，不能作为 2026-10-20 执行价格。
- 执行器 `checked_prices` 要求价格文件的 `verifiedDate` 等于执行当天、来源为 DeepSeek 官方价格页、模型/币种匹配；否则拒绝 live。
- 审批前必须重新取回官方价格页并生成当天价格文件；未核验时本包不可执行。

## 六、会发送 / 不会读取

会发送：

- 三个案例中固定的合成岗位要求、合成简历声明、证据片段、引用编号和历史解释；
- 当前版本提示词与工具 Schema；
- 模型生成的规划/分析内容只用于本机校验和后续固定输入。

不会读取或发送：

- 真实简历、真实个人材料、正常库报告、其他岗位报告、用户上传；
- 数据库凭据、DeepSeek Key、Cookie、MCP 凭据；
- 任何网络来源、未在包和源码哈希中固定的文件。

## 七、停止条件

任一条件发生即停止后续外发，保留已发出/可能已计费的请求：

1. 授权缺失、批次/包哈希不匹配、当天价格未核验；
2. `claim_batch` 已被占用、第二个执行者、输出文件已存在；
3. 每例超过 4 次或整批超过 12 次；
4. 输入超 20,000、输出 `max_tokens` 超 1,200、模型/提示词/工具 Schema 不符；
5. 请求上下文来源路径/要求不在固定案例内；
6. 发送后超时、断线、HTTP 错误或缺失/非法 usage；
7. 预算预留超过 2 元、写入报告/共享 claim 失败；
8. 最终分析未通过结构/grounding 校验后的定向修正仍失败。

失败状态分列：程序校验失败、供应商失败、模型合理停止、规则降级、结构通过但语义未评审。

## 八、执行后交付

- 3 例的 `toolCalls[]`、`requestCount`、实际 `attempts[]`（阶段、动态请求 SHA256、响应/usage）、`fallbackUsed`、`failureStage`、最终分析；
- 每例 `humanReview=null`，人工语义另行评审；
- `externalRequests`、`reservedYuan`、是否发生重试/超预算/停止；
- 若模型停止，保留；若程序跳过，单独标记；不为了“成功案例”改材料或加请求。

## 九、人工复核材料

复用现有三例真实响应，不再调用模型：

- [current-three-human-review.md](../20261017-task70-semantic-review-packet/current-three-human-review.md)
- 统一 rubric 与评审顺序：[REVIEWER-GUIDE.md](../20261017-task70-semantic-review-packet/REVIEWER-GUIDE.md)
- 当前人工完成数：**0/3**，语义通过率 **null**。
- 评审者先看输入/引用/原文，不看实现者参考或预期结论；评价引用支持、空实现/矛盾、夸大运行/贡献/能力、建议可执行性；允许“无法判断”。

## 十、审批勾选

- [ ] 确认三例合成输入及包哈希
- [ ] 确认工作树源码哈希/提交
- [ ] 确认每例 4 次、整批 12 次物理请求（含重试）
- [ ] 确认每次输入 20,000、输出 1,200 的硬边界
- [ ] 确认执行日官方价格及 2 元整批硬上限
- [ ] 确认旧 2026-10-18 三例授权不扩展
- [ ] 确认无真实个人材料/正常库/网络来源
- [ ] 确认停止条件与结果交付格式

未完成以上勾选和用户明确授权前，**不发送任何请求**。
