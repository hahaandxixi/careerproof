# E2E-03 学生 409/4097 根因审查（只读）

2026-10-05，个人GLM-5.3学生任务，HEAD 970c48a 现场核实，P2 stash 未动。审查对象：任务 `e3e3f88f-8d2e-491c-9353-2287cad54599` 的 lookup/GET 409。全部结论基于代码阅读 + `cp_e2e_closure-20261005` 只读查询（`SET default_transaction_read_only=on`），未做任何 SQL 修改、撤回、快照变更或业务库操作。未使用真实模型/真实简历/外发。

## 结论：夹具（fixture）问题，业务代码校验正确，不应放宽

- 业务口径：`AnalysisService` 正常报告 `candidate_ref = snapshot["candidateId"] = str(current_user.id)`（`backend/app/services/analysis.py:225` 落快照，`:675` 落库）。全仓业务消费方（`report_comparison.py:194` previous_comparison、`report_history.py:29` 历史选择）均按 **user.id** 口径匹配 candidate_ref，无任何业务方使用 profile.id 口径；前端不消费 candidateRef。
- 夹具偏差：`backend/evals/seed_e2e.py:469` 合成报告写 `candidate_ref=str(profile.id)`（StudentProfile UUID），与业务口径不一致。
- 后果链（本库已发生）：学生第一轮 chain-reply 在 **seed 合成报告 B** `73047c10`（candidate_ref=5613ac7e=profile.id）上创建补证任务 `e3e3f88f`，`base_snapshot.report.candidateId` 冻结为 5613ac7e；分析 `a0ef7a5a` 于 12:11:39 COMPLETED 并产生新报告 `3a78c342`（candidate_ref=d5e3f5be=user.id）。此后任何 `existing()` lookup 或任务 GET 走 `EvidenceGrowthService.view()` → `compare_views(base快照, 新报告)` → `base.candidate_id != target.candidate_id` → **409/4097「只能对比同一用户同一岗位的报告」**（`report_comparison.py:74-77`）。
- 数据事实证明**不是**真实跨用户/跨岗位：任务 created_by、两报告分析任务 created_by 均为同一 student 用户；base/target job_id 均为 `536f5d56`（岗位B）相同。校验拒绝的是夹具自相矛盾的 candidate 口径，不是越权访问。真实 UI baseline `1c421762`（12:11:00，candidate_ref=user.id）口径正确，从它创建的补证任务不会触发该 409。

详见 [db-readonly-evidence.json](db-readonly-evidence.json)（脱敏，仅 UUID/状态/时间）。观察到的 409 调用：`GET /match-reports/73047c10/growth-tasks/87278d08 → 409`（chain-reply 12:18:43.727Z 网络日志，`docs/evidence/20261005-E2E-student/chain-reply-2026-10-05T12-18-40-428Z/error-network-log.json`）；任务 GET 同路径。上一任务在 runner `seed-shape-comparison-blocked`（12:11:21 run）也已记录同一根因现象。

## 最小修复建议（交棒 Codex 裁决，不放宽跨用户校验）

- **推荐 A（一处夹具修复）**：`seed_e2e.py:469` 改 `candidate_ref=str(student_user_id)`，与 `analysis.py:225` 对齐。仅影响新 seed；`candidate_name` 维持合成标识不变。理由：业务唯一口径是 user.id，夹具应对齐业务而不是业务迁就夹具。
- **B（不改代码的运行侧出路）**：学生三变化链路改从真实 baseline `1c421762` 的 requirement 创建补证任务（口径正确，立即可用，不动任何数据）；合成报告 B 链路维持 blocked 留档为已知夹具限制。
- 存量数据处置（Codex 决定）：本库已存在的合成 A/B/A2 与任务 `e3e3f88f` 按合同不可 SQL 修改/撤回；若采用 A，后续新隔离库 seed 后即不复现。校验逻辑 `compare_views` 本身**不要改**。

## 附：本任务已完成的 runner 诊断修复（学生 helpers 范围内）

`scripts/e2e/student-browser-runner.mjs`（untracked，学生运行器）：上一任务把它改到一半被额度截断——8 个场景的 `try` 全部缺 `catch/finally`，`node --check` 直接语法错误，文件自 12:18:40 后无法运行。本次修复：

1. 每个场景 catch 按「**先在浏览器存活时转储**真实页面文本/截图/脱敏 network，**再**清理自有 Chrome，然后 rethrow」的顺序补齐（新增 `dumpFailureEvidence(tab)`，幂等；网络日志沿用既有脱敏口径：无 header/cookie，bodies 仅 UUID 截断）。
2. 外层 catch 保留兜底转储 + `activeBrowser.stop()`；`Chrome.stop()` 加 `closed` 幂等，杜绝双重 kill。
3. 显式声明 `let activeBrowser = null;`（原为 ESM 下会抛 ReferenceError 的隐式全局）。
4. 新增静态守卫测试 `scripts/e2e/student-runner-static.test.mjs`（6 项：语法、声明、dump-before-stop 时序 8 处、外层兜底、幂等）。本地测试 23/23 通过（6 静态 + 既有 `runner-input.test.mjs` 17）。未启动浏览器、未触服务。

## 未做/边界

- 未改任何产品源码（backend/jianli 只读）、未跑新 E2E 场景（runner 已修复可运行，但业务侧 409 属 Codex 裁决项，重跑 chain-reply 仍会在合成报告 B 上 blocked——那是真实业务拒绝，不是 runner 缺陷）。
- 未 Git 提交/推送、未动 P2 stash、未重启/迁移服务、未新建任务（复用 `e3e3f88f` 与既有 baseline）。
