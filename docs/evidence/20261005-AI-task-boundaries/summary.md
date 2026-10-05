# AI-01-R1 ZCode回归与证据：任务边界修复后的测试更新与工作流降级

日期：2026-10-05，基线 HEAD 70aafb0 + 工作区Codex改动（contracts.py、run_task_plan_quality.py、cases、task_boundaries.py）。无真实模型、网络、数据库、浏览器调用；未触碰产品码/运行器/cases/E2E/正式状态文档/Git提交。

## 本任务改动（仅限授权文件）

1. `backend/app/tests/test_task_plan_quality_coverage.py`：原四个红灯登记改为 `FORMER_REGISTERED_SEMANTIC_GAPS`，新增断言四个负例被实际拒绝（`accepted is False` 且期望匹配）；全套断言 23 探针期望全匹配、`suite_exit_ok` 为 True；新增正例保护测试（否定/待核验/未来补证措辞的四份参考草稿保持被接受）。cases 预期一字未改。
2. `backend/app/tests/test_task_boundaries.py`：新增两测试——四份案例参考草稿（含"待核验""不将参考实现计入个人证据""补齐缺失分支"等措辞）在真实来源文本下不被 `task_boundary_error` 拒绝；未来补交"本人贡献证明"交付物名称不被当作已证实贡献。
3. `backend/app/tests/test_task_plan_boundary_fallback.py`（新建）：工作流级真实回归，合成 provider 全离线：
   - 无效任务计划（小组报告替代个人贡献）→ 校验失败 → 安全降级：`fallback_used=True`、`analysis=None`（无可持久化对象，无效计划不存入任何报告）、`failure_stage="validation"`、规则证据保留。
   - 冲突来源静默采信计划 → 修复轮收到具名边界错误反馈（"omits unresolved implementation-source conflict"）→ 修复后仍无效 → 降级 `failure_stage="repair"`、`analysis=None`、无效计划不存。
   - 修复轮改为并列出处+待核验计划 → 修复成功（`repaired=True`），合法待核验计划被保留。
   - 合法个人边界计划直接通过、无需修复（正例对照，防过拟合误拒）。

## 复跑结果（完整原始输出与退出码见本目录各 console.txt）

| 项目 | 结果 | 退出码 |
| --- | --- | --- |
| 目标测试（3文件32用例） | 32 passed | 0 |
| 受影响 matcher/context/workflow（5文件86用例） | 86 passed | 0 |
| Ruff（3个目标测试文件） | All checks passed | 0 |
| 离线CLI authored-probes | 14样例/23探针，期望全匹配，正例14/14，externalCalls=0 | 0 |
| 离线CLI --responses 具名合成回放 | 同上 + replayedModelOutputs=1，independentSemanticReviews=0，semanticQualityPassRate=null | 0 |

四个原红灯（python-cache-partial、group-project-boundary、conflicting-export-materials、reference-only-sql 的对应负例）现已全部被契约实际拒绝，正例仍被接受。[Codex独立审计](../20261005-AI-codex-audit/summary.md)的旧红灯证据按原样保留，未被覆盖或删除。

## 词法范围与剩余限制（不可称全面语义可信）

- 边界守卫是窄词法检查：归属替代（参考/第三方/小组 + 作为/证明等 + 本人/个人 + 实践/能力/贡献等）、同主语"已实现/尚未实现"行首声明冲突、完整功能/链路验收需先核对或补全范围。仅识别明示措辞。
- 未验证：任意自然语言矛盾、隐性归属暗示、改写后的替代声明、跨文档多跳推理、真实模型是否真会产生这些错误。23 探针全部为作者合成夹具，不是独立语义标注；测试绿色仅证明契约与降级路径符合登记期望，真实回放/人工语义仍为 0/未验。
- 工作流降级测试使用与 [test_directed_retrieval.py 的 OfflinePlanner] 相同的合成 provider 接口（DeepSeekProvider 子类，覆盖 analyze_evidence，不发出网络请求）。

## 环境备注（非代码问题）

Windows 下 pytest `tmp_path` 在中文用户名临时目录 `C:\Users\江博\AppData\Local\Temp\pytest-of-江博` 上报 `PermissionError [WinError 5]`，影响 test_directed_retrieval.py 两个测试的夹具 setup。传 `--basetemp` 指向普通路径后 11/11 通过；受影响回归证据已用该方式重录。此问题先于本任务存在，建议后续在 CI/运行脚本中固定 `--basetemp` 或 `TMPDIR`。
