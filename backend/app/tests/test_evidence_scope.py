from dataclasses import replace
from uuid import uuid4

from app.agents.contracts import (
    AIRating,
    AIRequirementAnalysis,
    CriterionDecision,
    EvidenceAnalysis,
    ModelUsage,
)
from app.agents.evidence_scope import qualify_analysis
from app.agents.evidence_workflow import build_evidence_contexts
from app.tools.code_analyzer import CodeEvidence
from app.tools.matcher import MatchItemResult, MatchResult

UUID = "6db170c9-ea2b-4036-84d1-47260c687014"


def make_result():
    requirement_id = uuid4()
    evidence = [
        CodeEvidence(
            skill="pytest", evidence_type="pytest_test", file_path="tests/test_reg.py",
            line_start=1, line_end=3, snippet="def test_one():\n    assert True\n",
            strength="high", explanation="test", content_hash="a" * 64,
        ),
        CodeEvidence(
            skill="pytest", evidence_type="text", file_path=f"{UUID}/runtime/pytest-output.txt",
            line_start=1, line_end=2, snippet="11 passed\n", strength="medium",
            explanation="runtime", content_hash="b" * 64,
        ),
    ]
    item = MatchItemResult(
        requirement_id=requirement_id, requirement_title="pytest", skill="pytest",
        claimed=True, claim_text="test", evidence=evidence[0], evidence_list=evidence,
        verdict="supported", ai_confidence=None, rule_base_score=1, weight=3,
        final_score=1, explanation="rule", formula_version="evidence-v4",
    )
    return MatchResult(None, [item], [], [], "summary")


def make_analysis(result):
    requirement_id = result.items[0].requirement_id
    citation = build_evidence_contexts(result, max_evidence=1)[0].evidence[0].citation_id
    return EvidenceAnalysis(
        summary="summary", model="mock", usage=ModelUsage(input_tokens=1, output_tokens=1),
        items=[AIRequirementAnalysis(
            requirement_id=str(requirement_id),
            explanation="test",
            citation_ids=[citation],
            information_gap="未展示运行结果",
            suggestion="请补充运行结果",
            confidence=0.5,
            rating=AIRating(level=1, reason="test", criteria=[
                CriterionDecision(
                    criterion="relevance", supported=True,
                    citation_ids=[citation], reason="test",
                ),
                CriterionDecision(
                    criterion="operation", supported=False,
                    citation_ids=[], reason="test",
                ),
                CriterionDecision(
                    criterion="task", supported=False,
                    citation_ids=[], reason="test",
                ),
            ]),
        )],
    )


def test_unsent_rule_evidence_removes_absolute_missing_claim():
    result = make_result()
    contexts = build_evidence_contexts(result, max_evidence=1)
    qualified = qualify_analysis(make_analysis(result), result, contexts)
    item = qualified.items[0]
    assert "未展示" not in (item.information_gap or "")
    assert "请补充" not in (item.suggestion or "")
    assert "规则层另有未发送材料" in (item.information_gap or "")
    assert "runtime/pytest-output.txt" in (item.information_gap or "")
    assert "材料中可能已包含" in (item.suggestion or "")
    assert "runtime/pytest-output.txt 第1–2行" in (item.information_gap or "")
    assert UUID not in (item.information_gap or "")


def test_no_unsent_evidence_keeps_original_text():
    result = make_result()
    result = replace(
        result,
        items=[replace(result.items[0], evidence_list=result.items[0].evidence_list[:1])],
    )
    contexts = build_evidence_contexts(result, max_evidence=1)
    analysis = make_analysis(result)
    qualified = qualify_analysis(analysis, result, contexts)
    assert qualified.items[0].information_gap == "未展示运行结果"
