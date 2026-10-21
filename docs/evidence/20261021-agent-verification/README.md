# Agent 证据本地验证与预算账本（A/B/C 执行记录）

状态：A、B、C 已执行；D 尚未执行。未调用模型、未连接正常库/正常站。

## A 统一输入预算账本

提交：`f17be7a fix: unify Agent wire input budget accounting`

- 新增 `backend/app/agents/input_budget.py`：
  - `wire_payload_bytes` = 完整 request JSON 的 UTF-8 字节；
  - `estimate_wire_input_bytes` = UTF-8 bytes + `WIRE_SAFETY_MARGIN_BYTES=1024`；
  - 1024 明确为保守封装/转义余量，不是 token，也不重复计算 tools schema。
- `provider.py` 与 `ai_request_attempts.py` 使用同一函数；
- provider 的 preflight 字段改为 `utf8-wire-bytes-plus-safety-margin`，并记录 `safetyMarginBytes`;
- `estimate_evidence_input` 也按最终 request 的 wire 口径估算；
- 历史账目：规划 10,653 + 分析 38,846 = 49,499 bytes；42k 为历史拒绝，60k 对应本轮无工具、无修复；实际 usage 11,137 输入 / 1,679 输出。

测试：

- `76 passed, 5 skipped`（新增 `test_input_budget_ledger.py` 及相关预算/应用核验回归）；
- Ruff `All checks passed`；
- 原始输出：`docs/evidence/20261021-input-budget-ledger/tests.raw.out`；
- 对账：`docs/evidence/20261021-input-budget-ledger/budget-reconciliation.json`。

## B 本地证据验证器

提交：`e1064ec test: verify saved Agent evidence with local rules`

- 新增 `backend/evals/verify_agent_run.py`；
- 对真实报告 `f918...` 的结论：**pass**；
- 固定 V2 ZIP 路径/行号/片段校验通过；14 条证据引用；
- 五项、等级未超过本地 supported criteria 数、Redis 保持 gap/null；
- attempts 2、usage 11,137/1,679、费用 0.035706 元；
- 工具调用为 `not_requested / planner_declined`，在结果中列为 **UNVERIFIED**，不伪造成功；
- 错行号、错文件、越级、完成态工具无引用、缺 usage 的固定夹具测试均 FAIL。

证据：

- `verification.json`
- `claims.md`
- `backend/app/tests/test_agent_run_verification.py`（5 passed）

## C 源码等价与路径级检查

提交：`cf4572e`、`f1b26b0`、`869940a`

- `source-equivalence.json`：
  - 运行副本 `a571...` 在移除唯一诊断 print 后等于 `bcbe0e3` 的 `691d...`；
  - **historicalBusinessEquivalent=true**；
  - 当前 `f17be7a` 的 workflow 已因预算 estimator 标签/账本修复而变化；
  - **currentBusinessEquivalent=false**，不能声称旧报告与当前源码字节级一致；
- 路径级定义：
  - `run-paths.json` 列出实际运行/验证路径；
  - `check_run_paths.py` 对每个路径同时检查 git diff、untracked、SHA256；
  - 当前结果 `path-check.json`：**pass**；
  - 暂停的 6 个报告展示文件不在路径清单内、不进入运行副本。
- GPT 整改三态 triage：`docs/evidence/20261021-gpt-audit-triage/README.md`。
  - CI 远端：UNVERIFIED；
  - 账号注销 RESTRICT：静态开放，运行时 UNVERIFIED；
  - 过滤 pgvector：只做复核，运行时 UNVERIFIED，未改代码。

## 尚未执行

- C.1 真实工具用例：未获新模型授权/未执行；工具执行仍 UNVERIFIED。
- D 人工 3/3：仍 0/3，不新建空白草稿。
- 暂停的 mock 展示改动：未纳入，未修改。
- 源包、PDF 20–28 页、最终视频：未生成或未冻结。
- 页面和正常站验收未执行。

## 结论边界

- A/B/C 是本地代码与离线证据工作，不是真实 AI 工具能力验收；
- 旧报告内容通过本地 verifier，但**不是当前源码字节级**；
- 任何源包/PDF/视频冻结仍须 D 的真实人工和候选提交。
