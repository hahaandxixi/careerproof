# 完整五项报告输入预算预检（2026-10-21）

状态：**预检已完成；实际隔离运行见 [agent-live-20261021](agent-live-20261021/README.md)。**

## 结论

- 12,000 和 30,000 字符级上限不足以容纳完整五项 + 规划 + 最终分析。
- 42,000 仍在预算准入阶段触发 `report_input_token_limit`，未产生物理请求。
- 实际运行采用 **60,000 字符级输入上限 / 4,000 输出上限 / 3 条上下文**，2 次物理请求，实际输入 11,137 tokens、输出 1,679 tokens，费用 0.035706 元。
- 60,000 是本地 `conservative_input_token_estimate` 的 JSON 字符上限，不是供应商计费 token，也不代表每次请求实际会用满。

## 完整五项测量

| 组成 | 上界 |
| --- | ---: |
| 系统提示 | 5,339 |
| 证据片段（14 条 V2，含 Python cancel） | 约 11k |
| 五项判据 + 覆盖/要求/JSON 余量 | 约 9k |
| 完整分析消息（实际正式预检） | 27,725 |
| 规划实测（隔离运行前预算） | 4,108（正式 budget admission 约 10,653） |
| 实际输入 tokens | **11,137** |
| 完整修复代表值 | 约 27k |

完整五项**不能**用 12k/30k 单请求执行；42k 也在 budget admission 失败。60k 是本次实际通过的最小已测值，仍保留硬上限和全部证据，没有压缩或截断证据。

## 请求与费用

- 规划：1 次；最终分析：1 次；修复：0 次；物理请求 **2/12**。
- 实际 usage：输入 11,137 / 输出 1,679。
- 高峰价：0.035706 元；5 元上限远未触及。
- 自动重试：`DEEPSEEK_MAX_ATTEMPTS=1`。
- 预算 gate：inventory digest `05e51cd61442fe2b93343d811ae6ed779cafb4366384014d102eba5b70550ac6`。
- 旧三例授权包不可用：`code_analyzer.py`/`matcher.py` 哈希已变化，旧包检查返回 `SmokeStopped: Agent reviewed source changed`。

## 源码指纹

- `backend/app/core/config.py`：`1959307d269338fd7e1ae9f7bafc10afdac16b668629e09ec0a7ae9f5aa6d7e4`
- `backend/app/agents/evidence_workflow.py`：`691dbf73a46611c815b206ba6870cb9a6a7b332ccd0be34a7e8634b3eb6ac9cf`
- `backend/app/tools/code_analyzer.py`：`a353c2961474f04caf0cbf9aeb2c20f4e485f5ff3df9ab0f551f9264c8f57186`
- `backend/app/tools/matcher.py`：`8ca77bd966b79822fea1882ca5e8e164fd0aa6ca6e8b5f34992f44b6c6b3647d`

实际运行副本的 `evidence_workflow.py` 为 `a571a2...`，只多一行诊断 print；业务逻辑相同，未为对齐指纹重跑。

## 未完成

- 工具执行未发生；模型选择 `not_requested`。
- 页面、真人语义、独立用户未验。
- 旧授权/旧 claim 未复用。
- 不把等级不变或报告生成成功当作选证/语义正确。
