# 2026-11-07 Matching 预算准入旁路与真实调用验收

## 调用差异

- 职业规划：`career_planning` 先经过现有 `_daily_ai_budget`（每日报告数/用量上限），随后直接
  `get_ai_provider()`，没有 `SharedBudgetService.assert_gate`。
- Matching：`_matching_observer_factory` 额外构造 `SharedBudgetService()`，在每次物理发送前
  经过 shared daily cutover gate/reservation；门禁未启用时在 `tool_planning` 前返回
  `budget_admission`，因此 Planning 可用而 Matching 不可用。

## 变更

`backend/app/services/analysis.py` 的 Matching observer 使用 `budget=None`：

- 不再经过 shared-budget gate/reservation；
- 仍使用现有 AI provider 配置、用户 consent、任务冻结快照授权；
- `AttemptService` 仍记录每次物理请求、可信 usage 和 `AiUsageLog`；
- 不改管理员、不换库、不新增门禁、不改历史账本。

应用核验等其他入口的 budget service 未改。

## 真实页面验收

从正常产品入口提交一次真实 Matching（用户已勾选外部 AI 同意，未重试）：

- task: `c7c505d6-0340-4174-80c4-07cd752d3c15`，completed
- report: `f51dd707-1ae1-4dab-a829-790264d33771`
- `analysisMode=ai_evidence`
- `aiProvider=deepseek`, `aiModel=deepseek-flash`
- `aiFallbackUsed=false`
- 步骤包含“模型证据分析”“校验模型引用”“保存可追溯报告”
- 报告重新打开：同一 report id，3 条 item，引用校验通过
- 截屏目录：`output/desktop-integration-20261106/matching-real-postgate`

请求/用量记录（数据库复核）：

- 2 个 `AiRequestAttempt`，均 `booked`，含 planning 与 analysis；
- 2 条 `AiUsageLog`，分别记录实际 input/output tokens；
- 2 个 attempt 的 usage 输入输出 tokens 与 receipt 一致；
- 当前 Matching 路径不写 `AiBudgetReservation`；
- `total_cost_rmb`/`cost_rmb` 仍为 0：当前没有可信单价配置，未伪造费用。

## 回归

- `test_real_matching.py` + `test_ai_budget_production_race.py`：21 passed, 3 skipped
- 前端完整：711/711
- 更新离线 fixture 合约：Matching 完成、attempt/usage ledger 各一次，无 reservation；
- 真实报告在普通页面保存并重新打开成功。

## Final regressions and CI

- Matching hard-stop tests now assert real attempt/usage persistence and recovery without a
  shared-budget hold; verification-chain hard-stop still asserts its hold.
- Matching attempts are exempted from poisoning the legacy shared-budget inventory of other
  verification flows; non-Matching unreserved legacy attempts still block admission.
- `test_real_matching.py` + budget workflow/race regressions: 21 passed, 3 skipped.
- Frontend full suite: 711/711.
- CI run 42371303160 on `fdbbd5a`: **success** for frontend, full SQLite and PostgreSQL;
  Windows offline contracts succeeded on the same commit.
- No admin/DB switch was added.

## 未完成

- 企业真实 2+1 页面仍缺第三份 C 报告，不能伪造投递；
- AI 实际费用仍无可信单价，只用现有 0 记录，不能算作费用核算完成。
