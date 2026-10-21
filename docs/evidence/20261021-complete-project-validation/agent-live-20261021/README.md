# 完整五项真实 Agent 运行结果（2026-10-21）

状态：**一次隔离真实 DeepSeek 运行完成；不是页面/真人/独立用户验收。**

## 结果

- 报告：`f918f3d7-c4b3-4ae3-b48e-6c119e030628`
- Task：`32967100-77b7-456f-844b-a642e0b9e9a8`
- 模式：`ai_evidence`，provider `deepseek`
- 固定材料：V2 ZIP `58b3ced4e093d346b7f466d5cc36243639357590d8ab692445d6de9202fb1518`
- 五项齐全；FastAPI/SQL/Python/pytest 为 level 2，Redis 为 gap/null
- Python 引用：
  - `R3-E1` `storage.py:21-30`（BEGIN/commit/rollback）
  - `R3-E2` `service.py:25-54`（register）
  - `R3-E3` `service.py:56-77`（cancel）
- 工具观察：`retrieve_more_evidence` 为 `not_requested` / `planner_declined`；模型主动停止，没有工具执行。不能写成“工具调用成功”。
- 物理请求：**2**（1 规划 + 1 最终分析），无修复
- usage：输入 11,137，输出 1,679，缓存命中 4,480
- 高峰价估算：**0.035706 元**；低于 5 元上限
- 旧报告 `c97...`、`5960...` 读取前后不变
- 未打开页面；未操作正常库/正常站/8108/3108

## 预算与守卫

- `AI_PER_REPORT_INPUT_TOKEN_LIMIT=60000`（程序 JSON 字符上界，不是供应商计费 token）
- `AI_PER_REPORT_OUTPUT_TOKEN_LIMIT=4000`
- `AI_CONTEXT_EVIDENCE_LIMIT=3`
- `DEEPSEEK_MAX_ATTEMPTS=1`
- 日上限 250,000 输入 / 24,000 输出
- 预算 gate 已激活：inventory digest `05e51cd61442fe2b93343d811ae6ed779cafb4366384014d102eba5b70550ac6`
- 32k/42k 曾在预算准入阶段被拒，未产生物理请求；60k 才通过实际 budget admission。`60k` 是本地字符/容量上界，实际输入 11,137 tokens。

## 预检失败记录

四次预检失败（`cfd...`、`62c...`、`8ea...`、`23a...`）均未产生物理请求/usage：

1. 首次：规划预留不足，fallback；
2. 第二次：SQL 聚合查询错误（脚本问题）；
3. 第三次：`budget_cutover_not_enabled`；
4. 第四次：`report_input_token_limit`（42k 不足）。

这些失败任务已在隔离库中移除；对应失败 JSON 保留在 `live-result-failed-*.json`。旧报告未删除。

## 源码指纹与漂移说明

当前工作树源码：

- `config.py` `1959307d269338fd7e1ae9f7bafc10afdac16b668629e09ec0a7ae9f5aa6d7e4`
- `evidence_workflow.py` `691dbf73a46611c815b206ba6870cb9a6a7b332ccd0be34a7e8634b3eb6ac9cf`
- `code_analyzer.py` `a353c2961474f04caf0cbf9aeb2c20f4e485f5ff3df9ab0f551f9264c8f57186`
- `matcher.py` `8ca77bd966b79822fea1882ca5e8e164fd0aa6ca6e8b5f34992f44b6c6b3647d`

实际运行使用隔离副本的 `evidence_workflow.py` `a571a2...`：它是当前 `691dbf...` 加上一行诊断用 `print("WORKFLOW_EXC...")`，业务逻辑相同。**没有为了对齐指纹重跑第二次模型调用**；该差异必须保留说明，不能把运行源码说成与当前工作树逐字节相同。

## 文件

- `report-after.json`：真实五项报告
- `attempts.json` / `usage.json`：物理请求与 usage
- `live-result.json`：本次结果与成本
- `preflight.json`：离线输入预算
- `prices-20261021.json`：用户提供的高峰/空闲价
- `authorization-20261021.md`：授权范围
- `gate-activation.json`：预算 gate 激活
- `run_complete_agent.py`：单次执行器
- `run.raw.out` / `api.raw.out`

## 仍未解决

- 模型没有选择工具；只验证了“规划可停止”，未验证工具执行。
- 五项 AI 等级为 2/2/2/2/null；不据此升高或降低规则等级。
- 未打开页面、未做真人语义/独立用户验收。
- 旧三例授权不适用；旧 claim 未动。
