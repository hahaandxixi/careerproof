# 固定工具选择用例（离线）

状态：**仅离线 MockTransport 通过；未调用真实模型，工具执行仍 UNVERIFIED。**

## 范围

- 输入：V2 固定项目 Python 要求；
- 初始证据 2 条：`storage.py:21-30`、`service.py:25-54`；
- 第 3 条候选：`service.py:56-77`（cancel）；
- 要求模型通过 `retrieve_more_evidence` 补取第三条，最终引用新增候选；
- 守卫：最多 4 次物理请求、30,000 bytes 输入、4,000 输出；规划暴露工具，分析不得暴露工具；
- 离线 transport 只返回固定 planning tool call 和固定 analysis；不代表真实模型选择。

## 结果

`offline-result.json`：

- toolCalls：`retrieve_more_evidence` / completed / citationId `R1-E3`；
- analysisCitations：`R1-E3`；
- 2 次模型请求（离线 attempts），无 fallback；
- 初始上下文证据 2 条。

## 未验证

- 真实 DeepSeek 是否选择工具；
- 真实 tool-call 参数与引用；
- 真实 usage/费用；
- 任何页面。

未获新的真实模型授权，未运行 C.1 真实批次。
