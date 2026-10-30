# 固定工具选择用例

> **作用域（仅另一次运行）**：本文只描述另一次运行：输入/输出 **6,001 / 487**、估算费用 **0.015898 元**，工具 **`completed`** 并补取 **`R1-E3`**。它与 agent-verification 的 f918（11,137/1,679、0.035706 元、2 次请求、`planner_declined`）不是同一次，也未合并为同一次验收；两处结论不能互相替代。

状态：**离线通过；一次真实 DeepSeek 批次完成工具调用；人工评审仍不完整。**

## 范围

- 输入：V2 固定项目 Python 要求；
- 初始证据 2 条：`storage.py:21-30`、`service.py:25-54`；
- 第 3 条候选：`service.py:56-77`（cancel）；
- 要求模型通过 `retrieve_more_evidence` 补取第三条；
- 守卫：最多 4 次物理请求、30,000 bytes 输入、4,000 输出；规划暴露工具，分析不得暴露工具；
- 真实批次仅一次；`--live` 前已有新 claim，未重跑。

## 离线结果

`offline-result.json`：pass；工具 completed；引用 `R1-E3`；2 次 MockTransport 请求。

## 真实结果

`live-result.json`：

- 真实 provider：DeepSeek，2 次物理请求；
- 规划选择 `retrieve_more_evidence`，工具结果 completed，引用 `R1-E3`；
- 分析引用 `R1-E1`、`R1-E2`、`R1-E3`；
- 无 fallback；
- 输入 6,001 / 输出 487；
- 高峰价估算 0.015898 元；
- 未连接数据库/正常站。

说明：`live-result.json` 的原始 `status` 为 fail，原因是旧验收代码错误地要求引用列表**恰好等于** `["R1-E3"]`；实际要求是包含补取候选。已在 `tool_choice_smoke.py` 修正为“包含 R1-E3”。`live-acceptance.json` 记录按目标判据的 **pass**，没有第二次真实调用。

## 结论

- 工具真实调用已发生，且补取了 cancel 候选；
- 这仍只是一个单要求工具用例，不等于五项报告或整站通过；
- 人工评审仍不完整（另见 human-review-dwb）。

## 未验证

- 工具调用在五项完整报告中的表现；
- 页面；
- 人工语义 3/3。
