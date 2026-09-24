from uuid import uuid4

from app.models.enums import ConfirmationStatus
from app.schemas.analysis import CodeEvidenceView, MatchItemView
from app.services.action_plan import build_action_plan


def item(*, weight: int, level: int | None, ai: bool = False) -> MatchItemView:
    return MatchItemView.model_construct(
        requirement_id=uuid4(),
        requirement_title=f"要求 {weight}",
        skill="FastAPI",
        weight=weight,
        evidence_level=level,
        evidence_level_gap="补充可定位的实现材料。",
        confirmation_status=ConfirmationStatus.PENDING,
        ai_status="validated" if ai else "fallback",
        ai_suggestion="提交接口运行记录，并核对响应状态。" if ai else None,
        ai_information_gap="运行结果尚未核验。" if ai else None,
        ai_citation_ids=["R1-E1", "R1-E99"] if ai else [],
        evidence_list=[CodeEvidenceView.model_construct(citation_id="R1-E1")] if ai else [],
    )


def test_plan_prioritizes_high_weight_gaps_and_keeps_valid_citations() -> None:
    low = item(weight=2, level=1)
    ai = item(weight=5, level=2, ai=True)
    gap = item(weight=5, level=None)
    extra = item(weight=1, level=3)

    plan = build_action_plan([low, ai, gap, extra])

    assert [action.requirement_id for action in plan] == [
        gap.requirement_id,
        ai.requirement_id,
        low.requirement_id,
    ]
    assert plan[0].source == "rules"
    assert plan[1].source == "ai_suggestion"
    assert plan[1].citation_ids == ["R1-E1"]
    assert plan[1].action == ai.ai_suggestion
    assert plan[1].evidence_gap == ai.ai_information_gap


def test_reviewed_evidence_never_reuses_old_ai_advice_or_citations() -> None:
    reviewed = item(weight=5, level=None, ai=True)
    reviewed.confirmation_status = ConfirmationStatus.REJECTED

    plan = build_action_plan([reviewed])

    assert plan[0].source == "review"
    assert plan[0].citation_ids == []
    assert "重新发起分析" in plan[0].action
    assert build_action_plan([reviewed], limit=0) == []
