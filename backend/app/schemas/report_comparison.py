from uuid import UUID

from pydantic import Field

from app.schemas.analysis import CareerTaskPlan, CodeEvidenceView
from app.schemas.common import APIModel


class ComparisonItem(APIModel):
    requirement_id: UUID
    title: str
    status: str
    base_requirement: dict | None = None
    target_requirement: dict | None = None
    base_level: int | None = None
    target_level: int | None = None
    base_ai_status: str | None = None
    target_ai_status: str | None = None
    base_review: str | None = None
    target_review: str | None = None
    base_explanation: str | None = None
    target_explanation: str | None = None
    base_information_gap: str | None = None
    target_information_gap: str | None = None
    base_suggestion: str | None = None
    target_suggestion: str | None = None
    base_task_plan_warning: str | None = None
    target_task_plan_warning: str | None = None
    base_task_plan: CareerTaskPlan | None = None
    target_task_plan: CareerTaskPlan | None = None
    added_evidence: list[CodeEvidenceView] = Field(default_factory=list)
    removed_evidence: list[CodeEvidenceView] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)


class ReportComparison(APIModel):
    base_id: UUID
    target_id: UUID
    context_changes: list[str]
    base_materials: list[dict]
    target_materials: list[dict]
    items: list[ComparisonItem]
    limitations: list[str]
