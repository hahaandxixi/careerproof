# SEED-02 证据：合成报告身份与正式分析一致（candidate_ref 改用 User.id）

- 日期：2026-10-05；任务卡：`docs/task-cards/20261005-seed-candidate-identity.md`
- 执行：ZCode（GLM-5.3-Flash Start Plan 会话）；基线 HEAD `b8534ee27460e236417e355cb15b089b41e2640a`（未变，无 Git 提交/推送/stash）
- 允许改动范围执行情况：仅改 `backend/evals/seed_e2e.py`、`backend/app/tests/test_e2e_fixture_safety.py`；证据仅存本目录。产品协议/正式文档/student runner/旧 closure/audit 报告与快照零接触；未建库、未迁移、未重启服务、无浏览器/真实模型/外发；未重跑现有 seed、未倒写旧 fixture。

## 根因（与卡面一致，红测试实证）

`seed_e2e.py::_insert_student_report` 以 `candidate_ref=str(profile.id)` 写报告，而正式 `AnalysisService` 冻结 `candidateId=str(current_user.id)`（`app/services/analysis.py:225,675`）。`StudentProfile.id` 是独立于 `User.id` 的身份，故合成报告投递后学生侧任何按 user 身份的比较/历史查询（`report_comparison.py:77,194`、`report_history.py:29`）与正式报告语义不一致。

## 证据文件与命令（均在 `backend/` 目录下执行；Python 3.13.0，pytest 8.4.2，ruff 0.12.12）

沙箱限制系统临时目录写入，pytest 统一使用工作区临时目录 `--basetemp=.tmp/pytest-seed02 -p no:cacheprovider`（`backend/.tmp` 为 gitignored 状态目录）。

1. `red-test-output.txt` — 新增回归测试在修复前的真实红输出。
   `$ .venv/Scripts/python.exe -m pytest app/tests/test_e2e_fixture_safety.py::test_seeded_reports_freeze_account_user_id_as_candidate_identity -q -p no:cacheprovider --basetemp=.tmp/pytest-seed02`，退出码 **1**。
   断言差异即根因：报告 `candidate_ref`（profile.id，`a3823dbf-752…`）≠ 账号 `User.id`（`bdc348aa-94d…`）。仅在临时 SQLite/ASGI 夹具上运行。
2. `green-single-test-output.txt` — 修复后同一测试转绿，退出码 **0**（1 passed）。
3. `full-regression-output.txt` — 整份夹具回归（最终代码）。
   `$ .venv/Scripts/python.exe -m pytest app/tests/test_e2e_fixture_safety.py -q -p no:cacheprovider --basetemp=.tmp/pytest-seed02`，退出码 **0**（**18 passed**，含原有 17 项 + 新增 1 项；原材料引用行、通知计数、幂等/withdraw 行为均保持）。
4. `ruff-output.txt` — `$ .venv/Scripts/python.exe -m ruff check app/tests/test_e2e_fixture_safety.py evals/seed_e2e.py`，退出码 **0**（All checks passed）。
   附注：`ruff format --check` 对两文件提示重排，但 HEAD 原始版本同样不过（用 `git show HEAD:… | ruff format --check -` 验证，退出码均 1），属预先存在的仓库级漂移（抽测 `test_auth.py`、`analysis.py` 等 5 个未改文件同样不过，本仓库适用门槛为 `ruff check`）。本次新增/修改行已做到 format 兼容（`ruff format --diff` 中不再出现新测试相关行），未回写既有漂移行，保持最小 diff。
5. `fix.diff` — 两个允许文件相对 HEAD 的完整 diff。

## 修复内容（最小）

`backend/evals/seed_e2e.py::_insert_student_report` 一处行为变更：`candidate_ref=str(profile.id)` → `candidate_ref=str(student_user_id)`，并加两行约束注释。profile 存在校验（`if profile is None: raise IsolationError`）原样保留；简历 `Resume(student_id=profile.id)` 外键用法不变；compare_views/授权逻辑零改动。

新增测试 `test_seeded_reports_freeze_account_user_id_as_candidate_identity`：对 A/B/A2 三份报告断言 (1) `StudentProfile.id != User.id`（身份确属不同，保证断言有区分力）；(2) `MatchReport.candidate_ref == User.id`；(3) 投递冻结快照 `report_snapshot["candidateId"] == User.id`。仅修未来新 run 的种子身份；旧错误 fixture 不倒写，现有 run 验证行为不变。

## 脱敏说明

全部输出经扫描：无账号密码/token（state 文件口令从不打印，既有测试覆盖）、无真实个人信息、无本机用户名/绝对路径残留；仅含合成 UUID 与合成邮箱（`@e2e.example.com`）。合成夹具证据，非真实数据。
