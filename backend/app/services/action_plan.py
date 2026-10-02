"""Present validated per-requirement advice as a bounded, traceable plan.

The model supplies advice inside the existing evidence analysis. Ranking is
deterministic and does not create a new AI call or claim a higher rating.
"""

from app.models.enums import ConfirmationStatus
from app.schemas.analysis import EvidenceActionView, MatchItemView


def build_action_plan(items: list[MatchItemView], *, limit: int = 3) -> list[EvidenceActionView]:
    if limit < 1:
        return []
    ranked = sorted(
        enumerate(items),
        key=lambda indexed: (
            -indexed[1].weight,
            indexed[1].evidence_level if indexed[1].evidence_level is not None else 0,
            indexed[0],
        ),
    )
    plan: list[EvidenceActionView] = []
    for _, item in ranked:
        if item.confirmation_status in {ConfirmationStatus.REJECTED, ConfirmationStatus.CORRECTED}:
            source = "review"
            action = "核对复核意见，上传修正后的材料版本，再重新发起分析。"
            citations: list[str] = []
        elif (
            item.ai_status == "validated"
            and item.ai_suggestion
            and not item.ai_suggestion_redundant
        ):
            source = "ai_suggestion"
            action = item.ai_suggestion
            allowed = {evidence.citation_id for evidence in item.evidence_list}
            citations = [citation for citation in item.ai_citation_ids if citation in allowed]
        else:
            source = "rules"
            action = item.evidence_level_gap or "补充与岗位要求直接相关的可定位材料。"
            citations = []
        plan.append(
            EvidenceActionView(
                requirement_id=item.requirement_id,
                requirement_title=item.requirement_title,
                skill=item.skill,
                weight=item.weight,
                current_level=item.evidence_level,
                source=source,
                evidence_gap=(
                    item.ai_information_gap
                    if source == "ai_suggestion" and item.ai_information_gap
                    else item.evidence_level_gap
                ),
                action=action,
                citation_ids=citations,
            )
        )
        if len(plan) == limit:
            break
    return plan
