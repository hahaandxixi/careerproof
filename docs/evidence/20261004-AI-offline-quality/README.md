# AI-01 六类证据缺口离线覆盖：实施证据

执行者：ZCode（AI-01 有界离线实施），2026-10-05。代码基线 main@70aafb0。
授权范围：`backend/evals/task-plan-quality-cases.json`、`backend/evals/run_task_plan_quality.py`、新增 `backend/app/tests/test_task_plan_quality_coverage.py`、本目录。产品契约/检索协议未改动。

## 命令与退出码（全部离线，0外部调用，无凭据）

在 `backend/` 目录执行（`.venv/Scripts/python.exe`）：

1. 目标+受影响回归：`python -m pytest app/tests/test_task_plan_quality_coverage.py app/tests/test_matcher.py app/tests/test_evidence_context.py app/tests/test_ai_evidence_workflow.py -q -p no:cacheprovider`
   → `65 passed`，退出码 0。（`-p no:cacheprovider` 因本机对 `.pytest_cache` 写入报 WinError 5，仅影响缓存，不影响测试。）
2. `python -m ruff check evals/run_task_plan_quality.py app/tests/test_task_plan_quality_coverage.py` → `All checks passed!`，退出码 0。
3. 离线评测：`python evals/run_task_plan_quality.py --output .tmp/task-plan-quality-20261005-ai01-six-gap.json` → **退出码 1**（含4个登记红灯，见下）。原始标准输出：

```json
{"caseCount": 14, "sourceExactCount": 13, "sourceMismatchCount": 0, "noSourceCount": 1, "gapKindCoverage": {"contradictory-materials": 1, "contribution": 1, "execution": 5, "implementation": 1, "missing-run": 1, "partial-implementation": 1, "reference-only": 1, "review": 2, "unclear-contribution": 1}, "referenceContractAccepted": 14, "contractExpectationMatches": 19, "contractProbeCount": 23, "contractExpectationMismatches": [{"caseId": "python-cache-partial", "probeId": "partial-as-complete", "expectedContractRejection": true, "accepted": true}, {"caseId": "group-project-boundary", "probeId": "group-artifact-as-personal", "expectedContractRejection": true, "accepted": true}, {"caseId": "conflicting-export-materials", "probeId": "silent-pick-one-side", "expectedContractRejection": true, "accepted": true}, {"caseId": "reference-only-sql", "probeId": "reference-as-personal-practice", "expectedContractRejection": true, "accepted": true}], "replayedModelOutputs": 0, "independentSemanticReviews": 0, "semanticQualityPassRate": null}
```

报告JSON在被忽略路径 `backend/.tmp/task-plan-quality-20261005-ai01-six-gap.json`（保留失败证据，不覆盖旧基线）。

## 六类覆盖矩阵（契约拒绝 / 语义待验证 / 未覆盖 分列）

| 类别 | 具名case | 正例=authored参考草稿 | 负例探针 | 契约结果 | 语义状态 |
|---|---|---|---|---|---|
| 无实现 | `redis-unimplemented-first`（旧例保留） | 先补实现再运行 | `runtime-without-implementation` | **拒绝** ✓（`contracts.py:131` 显式未实现守卫） | 语义待人工 |
| 部分实现 | `python-cache-partial`（新） | 读路径/写路径分开列出 | `partial-as-complete` | **接受** → 红灯① | 未覆盖：契约无部分实现守卫 |
| 缺运行记录 | `api-run-record-missing`（新）；旧5个execution例rubric同向 | 命令+状态码+响应体+版本 | `source-as-runtime-proof` | **拒绝** ✓（`contracts.py:216` execution_claim 词法） | 语义待人工 |
| 个人贡献不明 | `group-project-boundary`（新）；旧 `event-planning-budget` | 具名提交+协作边界 | `group-artifact-as-personal` | **接受** → 红灯② | 未覆盖：无小组成果/个人贡献边界规则 |
| 相互矛盾材料 | `conflicting-export-materials`（新） | 并列出处+标记待核验 | `silent-pick-one-side` | **接受** → 红灯③ | 未覆盖：无冲突标记强制规则 |
| 仅参考材料 | `reference-only-sql`（新，走 `referenceFiles` 实际keyword接口） | 第三方标注+个人差距 | `reference-as-personal-practice` | **接受** → 红灯④ | 不变量成立：provenance=reference（`matcher.py:101,109`）、verdict不升（`matcher.py:124`）、rating_ceiling不升（`evidence_levels.py:92-94`）；但"参考当个人实践"的计划文本无守卫 |

旧9例与13个旧探针全部保留，期望未变；新矩阵另加5例10探针（23总探针，19匹配+4登记红灯）。

## 基线修正：sourceExact 空集合误判实锤

`docs/evidence/20261004-AI-baseline/summary.md` 报告 9/9 sourceExact。本次发现其中 **`postgres-query-execution` 实为 0 证据**（verdict=claimed_only，hybrid检索未命中），旧运行器 `all()` 对空集合真空为真（旧 `run_task_plan_quality.py` case_context），被计作"来源精确"。新运行器：空证据 → `sourceExact=False`、`sourceCheck="no-sources"`、单列 `noSourceCount=1`，不自动计充分，也**不**仅因缺证判失败（正确的无实现/降级草稿退出不受影响，`suite_exit_ok` 只看 mismatch）。来源核对与契约断言已分离为 `sourceCheck` 与 `contractExpectationMatched` 两条独立轴。

## 登记红灯（交Codex设计最小产品修复，本轮不改产品码）

现行草稿守卫仅三类：overclaim 词法（`contracts.py:191`）、重复索要已完整展示源码（`function_coverage.py:135`）、显式未实现却只要运行（`contracts.py:131`）。以下语义缺口现行契约拦不住，探针按"应拒绝"登记，运行器如实报 mismatch 并使退出码为1：

1. 部分实现当完整验收（`python-cache-partial/partial-as-complete`）
2. 小组成果当个人贡献（`group-project-boundary/group-artifact-as-personal`）
3. 冲突材料静默择一、不标待核验（`conflicting-export-materials/silent-pick-one-side`）
4. 第三方参考当个人实践证明（`reference-only-sql/reference-as-personal-practice`）

## 自审

- 运行器接 `referenceFiles`（matcher keyword-only 实际接口，与产品 `matching_materials.py:212-218,237` 同构：match 传 reference、enrich/原文核对传合并文件集）；规范化路径（`\`→`/`）后个人/参考碰撞与列表内重复路径先行拒绝（`case_files`），防字典覆盖混淆来源。
- 新旧兼容：旧9例 id、gapKind、knownBadDrafts id 由 `test_legacy_cases_and_probes_preserved` 锁定；`--responses` 回放门槛（syntheticDataOnly、唯一已知caseId）未动。
- 人工语义边界：`independentSemanticReviews=0`、逐例 `pending`、`semanticQualityPassRate=null` 在有回放时仍成立（`test_replay_does_not_raise_semantic_review_counts`）。本报告不填写任何人工评审结果。
- 结论分类：本轮全部为作者草稿契约探针；0真实模型调用、0回放、0独立人工语义；AI建议语义质量**未知**。

## 缺口与未验证项

- `postgres-query-execution` 零证据的检索层原因（hybrid_retrieval 未命中 `orders.py`）未深查，属产品检索行为，超出本轮授权。
- `--responses` 回放路径未做端到端CLI运行（仅单测覆盖不变量）。
- 四个红灯只证明"契约未拦住"，不代表草稿文本语义正确；独立人工语义复核仍为0/未知。
- `.pytest_cache`/`.ruff_cache` 写入被本机权限拒绝（WinError 5），以 `-p no:cacheprovider` 规避；`.tmp/` 评测输出写入正常。
- P2 stash、E2E-02 数据库/浏览器/运行器、正式状态文档均未触碰。
