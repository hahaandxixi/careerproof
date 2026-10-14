"""Goal 33: AI source-attribution and runtime-conclusion boundary tests.

Synthetic positive/negative examples run against the real current functions
(``validate_grounded_analysis`` and ``task_boundary_error``). The boundary
stays honest: guards fire only on explicit source facts, never on
inference; source-invisible residuals, negative/refusal wording and future
evidence-gathering plans keep the prior behavior. Original blind-review
labels and scores are not touched here.
"""

import pytest

from app.agents.contracts import (
    AIRequirementAnalysis,
    EvidenceAnalysis,
    EvidenceCandidate,
    EvidenceTaskPlan,
    RequirementEvidenceContext,
    plan_deployment_outcome_error,
    validate_grounded_analysis,
)
from app.tools.task_boundaries import task_boundary_error

SHARED_ACCOUNT_SOURCE = "仓库提交：全组共用账号，未区分作者"

FROZEN_EXTRACTION_PLAN = EvidenceTaskPlan(
    deliverable="本人在小组项目中的具名提交清单",
    steps=["从版本历史筛出本人署名的提交", "标注每项提交对应的责任范围"],
    acceptance_checks=["提交记录包含作者与时间", "责任范围与岗位要求逐条对应"],
)

E2FD_NEUTRAL_V1 = EvidenceTaskPlan(
    deliverable="已部署接口证明",
    steps=["整理 metrics.py 源码文件"],
    acceptance_checks=["源码存在即证明线上接口稳定运行"],
)

E2FD_FROZEN_ORIGINAL = EvidenceTaskPlan(
    deliverable="已部署接口证明",
    steps=["将代码文件当作已通过运行测试的证据提交"],
    acceptance_checks=["源码存在即证明线上接口稳定运行"],
)


def supported_python_context():
    return RequirementEvidenceContext(
        requirement_id="goal33-py-total",
        requirement_title="实现 Python 数值汇总函数并保存输入输出记录",
        skill="Python", verdict="supported", rule_score=0.65, claimed=True,
        evidence=[EvidenceCandidate(
            citation_id="R1-E1", file_path="metrics.py", line_start=1, line_end=1,
            evidence_type="python_code", strength="high", snippet="def total(values):",
        )],
    )


def shared_account_context(evidence_visible=True):
    evidence = [EvidenceCandidate(
        citation_id="R1-E1", file_path="group_report.md", line_start=5, line_end=5,
        evidence_type="semantic_document_candidate", strength="low",
        snippet=SHARED_ACCOUNT_SOURCE,
    )] if evidence_visible else []
    return RequirementEvidenceContext(
        requirement_id="goal33-shared-account",
        requirement_title="说明本人负责的后端模块范围",
        skill="Python", verdict="claimed_only", rule_score=0.1, claimed=True,
        evidence=evidence,
    )


def analysis(context, plan):
    return EvidenceAnalysis(
        summary="仅检查合成任务计划的结构边界。",
        model="synthetic-goal33",
        items=[AIRequirementAnalysis(
            requirement_id=context.requirement_id,
            explanation="仅核对计划文本与来源事实的结构一致性。",
            citation_ids=[e.citation_id for e in context.evidence]
            if context.verdict in {"supported", "partial"} else [],
            information_gap="运行结果、部署情况与本人贡献仍需核验。",
            suggestion="补充运行记录或独立贡献证明后再核验。",
            task_plan=plan, confidence=0,
        )],
    )


# --- Rule A: source presence cannot prove a deployment/runtime outcome. ---


def test_source_presence_causal_runtime_claim_is_rejected():
    context = supported_python_context()
    with pytest.raises(ValueError, match="deployment or runtime"):
        validate_grounded_analysis([context], analysis(context, E2FD_NEUTRAL_V1))


def test_runtime_keyword_in_steps_cannot_bypass_causal_claim():
    context = supported_python_context()
    plan = E2FD_NEUTRAL_V1.model_copy(
        update={"steps": ["整理 metrics.py 源码文件并运行一次"]}
    )
    with pytest.raises(ValueError, match="deployment or runtime"):
        validate_grounded_analysis([context], analysis(context, plan))


def test_runtime_records_elsewhere_cannot_bypass_causal_acceptance():
    context = supported_python_context()
    plan = E2FD_NEUTRAL_V1.model_copy(
        update={"steps": ["调用接口并保存响应与时间戳"]}
    )
    with pytest.raises(ValueError, match="deployment or runtime"):
        validate_grounded_analysis([context], analysis(context, plan))


def test_deployment_outcome_without_record_step_is_rejected():
    context = supported_python_context()
    plan = EvidenceTaskPlan(
        deliverable="已部署接口证明",
        steps=["整理 metrics.py 源码文件"],
        acceptance_checks=["接口在服务器上稳定运行"],
    )
    with pytest.raises(ValueError, match="without a runtime-record step"):
        validate_grounded_analysis([context], analysis(context, plan))


def test_causal_claim_inside_a_step_is_rejected():
    context = supported_python_context()
    plan = EvidenceTaskPlan(
        deliverable="部署取证记录",
        steps=["将源码存在作为部署证明归档", "调用接口并保存响应与时间戳"],
        acceptance_checks=["响应与时间戳可对应部署版本"],
    )
    with pytest.raises(ValueError, match="deployment or runtime"):
        validate_grounded_analysis([context], analysis(context, plan))


def test_outcome_asserted_only_in_acceptance_without_record_step_is_rejected():
    context = supported_python_context()
    plan = EvidenceTaskPlan(
        deliverable="部署情况说明",
        steps=["整理 metrics.py 源码文件"],
        acceptance_checks=["接口在服务器上稳定运行"],
    )
    with pytest.raises(ValueError, match="without a runtime-record step"):
        validate_grounded_analysis([context], analysis(context, plan))


def test_future_deployment_evidence_plan_is_allowed():
    context = supported_python_context()
    gathering = EvidenceTaskPlan(
        deliverable="部署取证记录",
        steps=["调用接口并保存响应与时间戳"],
        acceptance_checks=["响应与时间戳可对应部署版本"],
    )
    outcome_with_records = E2FD_NEUTRAL_V1.model_copy(
        update={
            "steps": ["调用接口并保存响应与时间戳"],
            "acceptance_checks": ["响应与时间戳可对应部署版本"],
        }
    )
    for plan in (gathering, outcome_with_records):
        validate_grounded_analysis([context], analysis(context, plan))


def test_negative_conditional_and_refusal_runtime_wording_is_allowed():
    context = supported_python_context()
    refusal = E2FD_NEUTRAL_V1.model_copy(update={
        "deliverable": "部署情况说明",
        "acceptance_checks": ["源码存在不代表线上接口稳定运行，仍需运行记录核验"],
    })
    conditional = EvidenceTaskPlan(
        deliverable="部署情况说明",
        steps=["记录接口响应"],
        acceptance_checks=["验证接口是否稳定运行并保存响应"],
    )
    for plan in (refusal, conditional):
        validate_grounded_analysis([context], analysis(context, plan))


def test_frozen_e2fd_rejection_keeps_existing_wording_guard():
    context = supported_python_context()
    with pytest.raises(ValueError, match="unsupported ability or execution claim"):
        validate_grounded_analysis([context], analysis(context, E2FD_FROZEN_ORIGINAL))


# --- Rule B: shared-account history cannot yield a personal-signed extract. ---


def test_shared_account_history_extraction_is_rejected():
    error = task_boundary_error(
        deliverable=FROZEN_EXTRACTION_PLAN.deliverable,
        steps=list(FROZEN_EXTRACTION_PLAN.steps),
        acceptance_checks=list(FROZEN_EXTRACTION_PLAN.acceptance_checks),
        personal_source_texts=[SHARED_ACCOUNT_SOURCE],
    )
    assert error is not None
    assert "shared-account" in error


def test_source_visible_shared_account_contract_rejects_extraction():
    context = shared_account_context()
    with pytest.raises(ValueError, match="shared-account"):
        validate_grounded_analysis([context], analysis(context, FROZEN_EXTRACTION_PLAN))


def test_independent_named_proof_with_pending_state_is_allowed():
    assert task_boundary_error(
        deliverable="本人贡献证明补交计划",
        steps=["先核对共用账号不能区分作者的边界，再补交独立具名的分工证明"],
        acceptance_checks=["贡献在独立材料核验前仍待核验"],
        personal_source_texts=[SHARED_ACCOUNT_SOURCE],
    ) is None


def test_full_contract_allows_independent_named_proof_plan():
    context = shared_account_context()
    plan = EvidenceTaskPlan(
        deliverable="本人贡献证明补交计划",
        steps=["先核对共用账号不能区分作者的边界，再补交独立具名的分工证明"],
        acceptance_checks=["贡献在独立材料核验前仍待核验"],
    )
    validate_grounded_analysis([context], analysis(context, plan))


def test_shared_account_without_impossibility_fact_allows_extraction_plan():
    assert task_boundary_error(
        deliverable=FROZEN_EXTRACTION_PLAN.deliverable,
        steps=list(FROZEN_EXTRACTION_PLAN.steps),
        acceptance_checks=list(FROZEN_EXTRACTION_PLAN.acceptance_checks),
        personal_source_texts=["仓库提交：全组共用账号"],
    ) is None


def test_history_conditional_and_negative_source_wording_do_not_trigger():
    sources = [
        "此前仓库曾用共用账号，现已区分作者",
        "如果共用账号未区分作者，应在计划中说明局限",
        "本项目未使用共用账号，提交可区分作者",
    ]
    for source in sources:
        assert task_boundary_error(
            deliverable=FROZEN_EXTRACTION_PLAN.deliverable,
            steps=list(FROZEN_EXTRACTION_PLAN.steps),
            acceptance_checks=list(FROZEN_EXTRACTION_PLAN.acceptance_checks),
            personal_source_texts=[source],
        ) is None, source


def test_paraphrased_refusal_in_plan_is_not_extraction():
    assert task_boundary_error(
        deliverable="个人贡献来源说明",
        steps=["说明无法从版本历史筛出本人署名的提交，改为引用分工附件"],
        acceptance_checks=["说明保留待核验边界"],
        personal_source_texts=[SHARED_ACCOUNT_SOURCE],
    ) is None


def test_source_invisible_residual_keeps_old_acceptance():
    context = shared_account_context(evidence_visible=False)
    validate_grounded_analysis([context], analysis(context, FROZEN_EXTRACTION_PLAN))
    assert task_boundary_error(
        deliverable=FROZEN_EXTRACTION_PLAN.deliverable,
        steps=list(FROZEN_EXTRACTION_PLAN.steps),
        acceptance_checks=list(FROZEN_EXTRACTION_PLAN.acceptance_checks),
        personal_source_texts=[],
    ) is None


# --- Prior contract behavior stays intact. ---


def test_existing_contract_rejections_stay_intact():
    context = supported_python_context()
    vague = EvidenceTaskPlan(
        deliverable="进一步完善岗位材料",
        steps=["材料满足岗位要求"],
        acceptance_checks=["内容得到有效完善"],
    )
    with pytest.raises(ValueError, match="unsupported ability or execution claim"):
        validate_grounded_analysis([context], analysis(context, vague))

    redis_source = EvidenceCandidate(
        citation_id="R1-E1", file_path="README.md", line_start=1, line_end=1,
        evidence_type="retrieved_context", strength="low",
        snippet="Redis 未实现，当前只有缓存需求说明。",
    )
    redis_context = RequirementEvidenceContext(
        requirement_id="goal33-redis",
        requirement_title="实现 Redis 缓存读写并说明键设计",
        skill="Redis", verdict="claimed_only", rule_score=0.1, claimed=True,
        evidence=[redis_source],
    )
    runtime_only = EvidenceTaskPlan(
        deliverable="Redis 运行日志",
        steps=["执行缓存读写并保存输出"],
        acceptance_checks=["日志显示返回状态"],
    )
    with pytest.raises(ValueError, match="execution before missing implementation"):
        validate_grounded_analysis([redis_context], analysis(redis_context, runtime_only))


# --- Goal 36: material wording is not a causal claim; negation stays clause-local. ---


def goal36_plan(acceptance_check: str) -> EvidenceTaskPlan:
    return EvidenceTaskPlan(
        deliverable="部署情况说明",
        steps=["整理 metrics.py 源码文件"],
        acceptance_checks=[acceptance_check],
    )


# Codex-reproduced false positives: existence + material fact, runtime still pending.
LEGAL_MATERIAL_WORDING = [
    "源码存在说明文件已经上传，实际运行仍待核验",
    "源码存在证明材料可定位，部署结果需要另行核验",
]


def test_material_upload_and_location_wording_is_allowed():
    context = supported_python_context()
    for phrase in LEGAL_MATERIAL_WORDING:
        assert plan_deployment_outcome_error(
            "部署情况说明", ["整理 metrics.py 源码文件"], [phrase]
        ) is None, phrase
        validate_grounded_analysis([context], analysis(context, goal36_plan(phrase)))


def test_unproved_negated_connector_is_allowed():
    context = supported_python_context()
    for phrase in ("源码存在未证明部署成功", "源码存在不等同于已部署"):
        assert plan_deployment_outcome_error(
            "部署情况说明", ["整理 metrics.py 源码文件"], [phrase]
        ) is None, phrase
        validate_grounded_analysis([context], analysis(context, goal36_plan(phrase)))


def test_meaning_connector_causal_claim_is_still_rejected():
    phrase = "源码存在意味着线上可用"
    error = plan_deployment_outcome_error(
        "部署情况说明", ["整理 metrics.py 源码文件"], [phrase]
    )
    assert error is not None and "deployment or runtime" in error


def test_pending_negation_clause_does_not_exempt_independent_causal_error():
    context = supported_python_context()
    phrase = "实际运行仍待核验，源码存在说明部署成功"
    error = plan_deployment_outcome_error(
        "部署情况说明", ["整理 metrics.py 源码文件"], [phrase]
    )
    assert error is not None and "deployment or runtime" in error
    with pytest.raises(ValueError, match="deployment or runtime"):
        validate_grounded_analysis([context], analysis(context, goal36_plan(phrase)))


def test_pending_negation_clause_does_not_mask_independent_outcome_assertion():
    # Codex holdout: a pending/negated clause must not mask an independent
    # deployment conclusion after the comma (no runtime-record step present).
    context = supported_python_context()
    for phrase in (
        "部署是否成功待核验，但服务器已稳定运行",
        "本人贡献待核验，接口已部署",
    ):
        error = plan_deployment_outcome_error(
            "部署情况说明", ["整理 metrics.py 源码文件"], [phrase]
        )
        assert error is not None and "without a runtime-record step" in error, phrase
        with pytest.raises(ValueError, match="without a runtime-record step"):
            validate_grounded_analysis([context], analysis(context, goal36_plan(phrase)))
    # Real future/negative plans stay allowed alongside the tightened scope.
    assert plan_deployment_outcome_error(
        "部署取证记录",
        ["运行服务后保存日志"],
        ["核验是否已部署，响应与时间戳待归档"],
    ) is None
    assert plan_deployment_outcome_error(
        "部署取证记录",
        ["调用接口并保存响应与时间戳"],
        ["已部署版本待核验，结果另行核验"],
    ) is None
