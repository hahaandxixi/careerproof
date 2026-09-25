import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agents.contracts import (
    EvidenceAnalysis,
    RequirementEvidenceContext,
    overclaim_flags,
    validate_grounded_analysis,
)
from app.agents.evidence_workflow import build_evidence_contexts, run_evidence_workflow
from app.agents.provider import evidence_analysis_messages
from app.core.config import settings
from app.tests.test_ai_evidence_workflow import evidenced_result
from app.tools.evidence_levels import classify_evidence
from app.tools.skill_rubric import rubric_for


def sample():
    contexts = build_evidence_contexts(evidenced_result())
    context = contexts[0]
    citation = context.evidence[0].citation_id
    answer = dict(
        summary="材料展示接口相关声明。",
        model="synthetic",
        items=[
            dict(
                requirement_id=context.requirement_id,
                explanation="可见函数体为空。",
                citation_ids=[citation],
                information_gap="实际处理与运行记录待补充。",
                suggestion="补充实现与验证材料。",
                confidence=0.6,
                rating=dict(
                    level=1,
                    reason="空函数仅提供相关线索。",
                    criteria=[
                        dict(
                            criterion=key,
                            supported=key == "relevance",
                            citation_ids=[citation] if key == "relevance" else [],
                            reason="存在相关名称，未展示实质处理。",
                        )
                        for key in ("relevance", "operation", "task")
                    ],
                ),
            )
        ],
    )
    return contexts, answer


def test_empty_implementation_can_be_lowered_by_ai_and_review_suspends():
    contexts, answer = sample()
    analysis = EvidenceAnalysis.model_validate(answer)
    validate_grounded_analysis(contexts, analysis)
    snapshot = dict(skill="FastAPI", evidenceList=[e.model_dump() for e in contexts[0].evidence])
    before = classify_evidence(snapshot, "supported")
    assert before["evidence_level"] == 2
    snapshot["ai"] = dict(
        status="validated",
        rating=answer["items"][0]["rating"],
        ratingRubric=contexts[0].rating_rubric,
    )
    assert classify_evidence(snapshot, "supported")["evidence_level"] == 1
    assert classify_evidence(snapshot, "supported")["evidence_level_source"] == "ai_preliminary"
    assert classify_evidence(snapshot, "supported", "rejected")["evidence_level"] is None
    assert classify_evidence(snapshot, "supported", "accepted")["evidence_level"] == 1


@pytest.mark.parametrize(
    "fault",
    ["missing", "citation", "duplicate", "prerequisite", "level", "ceiling", "overclaim", "four"],
)
def test_invalid_ai_ratings_are_rejected(fault):
    contexts, answer = sample()
    item = answer["items"][0]
    rating = item["rating"]
    if fault == "missing":
        item.pop("rating")
    elif fault == "citation":
        rating["criteria"][0]["citation_ids"] = ["R99-E1"]
    elif fault == "duplicate":
        rating["criteria"][1] = deepcopy(rating["criteria"][0])
    elif fault == "prerequisite":
        rating["criteria"][0]["supported"] = False
        rating["criteria"][1].update(supported=True, citation_ids=item["citation_ids"])
    elif fault == "level":
        rating["level"] = 2
    elif fault == "ceiling":
        contexts[0].rating_ceiling = None
    elif fault == "overclaim":
        rating["reason"] = "证明具备开发能力"
    else:
        rating["level"] = 4
    with pytest.raises((ValueError, ValidationError)):
        validate_grounded_analysis(contexts, EvidenceAnalysis.model_validate(answer))


async def test_workflow_accepts_ai_rating_and_falls_back_on_invalid_rating(monkeypatch):
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    invalid = False

    class Provider:
        name = "synthetic"

        async def analyze_evidence(self, *, contexts):
            _, answer = sample()
            answer["items"][0]["requirement_id"] = contexts[0].requirement_id
            if invalid:
                answer["items"][0]["rating"]["level"] = 3
            return EvidenceAnalysis.model_validate(answer)

    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", Provider)
    result = evidenced_result()
    success = await run_evidence_workflow(result)
    assert success.analysis.items[0].rating.level == 1
    invalid = True
    fallback = await run_evidence_workflow(result)
    assert fallback.analysis is None and fallback.fallback_used
    assert fallback.fallback_reason == "invalid_output_or_config"


def test_dependency_cannot_support_operation_even_with_higher_global_ceiling():
    contexts, answer = sample()
    item = answer["items"][0]
    contexts[0].evidence[0].evidence_type = "dependency"
    contexts[0].rating_ceiling = 3
    item["rating"]["level"] = 2
    item["rating"]["criteria"][1].update(supported=True, citation_ids=item["citation_ids"])
    with pytest.raises(ValueError, match="citations cannot support"):
        validate_grounded_analysis(contexts, EvidenceAnalysis.model_validate(answer))


def test_legacy_ai_explanation_does_not_become_an_ai_rating():
    snapshot = {
        "evidenceList": [{"evidence_type": "python_code", "context_complete": True}],
        "ai": {"status": "validated", "explanation": "历史模型摘要"},
    }
    result = classify_evidence(snapshot, "supported")
    assert result["evidence_level_source"] == "rules"
    assert result["evidence_level"] == 3
    assert result["rating_criteria"] == []


def test_backup_dependency_alone_is_only_a_clue():
    result = classify_evidence(
        {"skill": "备份恢复", "evidenceList": [{"evidence_type": "dependency"}]}, "partial"
    )
    assert result["evidence_level"] == 1


def test_postgres_usage_allows_operation_but_not_complete_task_by_rule():
    result = classify_evidence(
        {
            "skill": "PostgreSQL",
            "evidenceList": [
                {
                    "evidence_type": "postgres_usage",
                    "context_complete": True,
                    "snippet": (
                        "def find(conn, task_id):\n"
                        "    return conn.execute('SELECT title FROM tasks WHERE id = %s', "
                        "(task_id,)).fetchone()"
                    ),
                }
            ],
        },
        "partial",
    )
    assert result["evidence_level"] == 2
    assert result["evidence_level_label"] == "局部操作"


def test_relevance_rubric_wording_is_not_job_fitness():
    assert overclaim_flags("存在 FastAPI 路由定义，满足相关性要求。") == []
    assert overclaim_flags("满足岗位要求")
    assert overclaim_flags("满足相关性要求，证明具备开发能力")


def test_complete_function_cannot_be_described_as_unseen_in_gap():
    contexts, answer = sample()
    contexts[0].evidence[0].context_complete = True
    contexts[0].evidence[0].snippet = "@app.get('/health')\ndef health():\n    pass"
    answer["items"][0]["information_gap"] = "未核验函数体是否包含数据处理逻辑。"
    with pytest.raises(ValueError, match="contradicts the complete function context"):
        validate_grounded_analysis(contexts, EvidenceAnalysis.model_validate(answer))


def test_skill_rubric_defines_specific_task_boundary():
    fastapi = rubric_for("FastAPI")
    backup = rubric_for("备份恢复")
    postgres = rubric_for("PostgreSQL")
    assert "明确返回" in fastapi["criteria"]["task"]
    assert "测试请求与结果断言" in fastapi["criteria"]["task"]
    assert "一致性核验" in backup["criteria"]["task"]
    assert "参数化" in postgres["criteria"]["operation"]
    assert "执行" in postgres["criteria"]["operation"]
    assert "至少一个" in postgres["criteria"]["operation"]
    assert "不要求覆盖" in postgres["criteria"]["operation"]
    assert "逐项覆盖" in postgres["criteria"]["task"]
    assert "不推断数据库已连接" in postgres["criteria"]["task"]
    assert fastapi["path"] == ["后端开发", "FastAPI"]


def test_real_report_cannot_rate_composite_fastapi_task_without_test_assertions():
    source = (
        Path(__file__).resolve().parents[2]
        / "evals/deepseek-two-rounds-20260925-150929.json"
    )
    saved = json.loads(source.read_text(encoding="utf-8"))
    contexts = [RequirementEvidenceContext.model_validate(item) for item in saved["contexts"]]
    analysis = EvidenceAnalysis.model_validate(saved["analysis"])

    with pytest.raises(ValueError, match="lacks cited test assertions"):
        validate_grounded_analysis(contexts, analysis)


def test_prompt_keeps_operation_separate_from_task_completeness():
    contexts, _answer = sample()
    system = evidence_analysis_messages(contexts)[0]["content"]
    assert "不能据此把已经明确展示的实质操作判为operation=false" in system
    assert "避免使用满足岗位要求或不满足岗位要求" in system
