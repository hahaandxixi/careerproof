from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from app.models.enums import ConfirmationStatus, TaskStatus
from app.schemas.common import APIModel
from app.schemas.visual import VisualReviewView


class MaterialSelection(APIModel):
    resume_version_id: UUID
    project_version_ids: list[UUID] = Field(default_factory=list, max_length=10)


class MatchCreate(MaterialSelection):
    job_id: UUID
    external_ai_consent: bool = False
    use_previous_report: bool = False


class JobRecommendationRequest(MaterialSelection):
    limit: int = Field(default=5, ge=1, le=10)


class CareerPlanRequest(JobRecommendationRequest):
    external_ai_consent: bool = False


class RecommendationEvidence(APIModel):
    citation_id: str | None = None
    project_file_id: UUID | None = None
    project_version_id: UUID | None = None
    skill: str
    file_path: str
    line_start: int
    line_end: int
    strength: str
    explanation: str
    snippet: Annotated[str, StringConstraints(strip_whitespace=False)] = ""
    content_hash: str = ""


class RecommendationRequirement(APIModel):
    text: str
    skill: str
    weight: int
    is_required: bool
    rule_verdict: str


class JobRecommendationView(APIModel):
    job_id: UUID
    job_title: str
    company_name: str
    category: str
    city: str
    employment_type: str
    priority: str
    assessed_count: int
    requirement_count: int
    supported_count: int
    claimed_count: int
    matched_skills: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    requirements: list[RecommendationRequirement] = Field(default_factory=list)
    evidence: list[RecommendationEvidence] = Field(default_factory=list)


class ReportMaterial(APIModel):
    kind: str
    id: UUID
    title: str
    version_number: int
    material_role: Literal["portfolio", "reference"] | None = None
    content_hash: str


class JobRecommendationResult(APIModel):
    primary_direction: str | None = None
    summary: str
    materials: list[ReportMaterial] = Field(default_factory=list)
    recommendations: list[JobRecommendationView] = Field(default_factory=list)


class CareerTaskPlan(APIModel):
    deliverable: str = Field(min_length=1, max_length=200)
    steps: list[str] = Field(min_length=1, max_length=4)
    acceptance_checks: list[str] = Field(min_length=1, max_length=4)


class CareerAdvice(APIModel):
    job_id: UUID
    reason: str = Field(min_length=1, max_length=300)
    key_gap: str = Field(min_length=1, max_length=300)
    next_task: str = Field(min_length=1, max_length=300)
    task_plan: CareerTaskPlan | None = None
    citation_ids: list[str] = Field(default_factory=list, max_length=3)


class CareerPlanAnalysis(APIModel):
    comparison: str = Field(min_length=1, max_length=600)
    focus_job_id: UUID | None = None
    advice: list[CareerAdvice] = Field(min_length=1, max_length=3)


class CareerPlanChange(APIModel):
    job_id: UUID
    job_title: str
    status: Literal["current", "not_in_current"] = "current"
    previous_supported_count: int | None = None
    current_supported_count: int | None = None
    previous_priority: str | None = None
    current_priority: str | None = None
    detail: str
    materials_changed: bool = False
    requirements_changed: bool = False
    job_details_changed: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class CareerValidationIssue(APIModel):
    reason: str = Field(min_length=1, max_length=200)
    rejected_claim: str = Field(min_length=1, max_length=220)
    citation_ids: list[str] = Field(default_factory=list, max_length=3)


class CareerPlanResult(JobRecommendationResult):
    plan_id: UUID | None = None
    previous_plan_id: UUID | None = None
    ai_plan: CareerPlanAnalysis | None = None
    ai_fallback_used: bool = False
    ai_status: str = "not_requested"
    ai_model: str | None = None
    ai_usage: dict | None = None
    ai_validation_issues: list[CareerValidationIssue] = Field(default_factory=list, max_length=3)
    changes: list[CareerPlanChange] = Field(default_factory=list)


class TaskAccepted(APIModel):
    task_id: UUID
    status: TaskStatus


class AgentStepView(APIModel):
    step: int
    event_type: str
    name: str
    detail: str
    payload: dict = Field(default_factory=dict)


class AnalysisTaskView(APIModel):
    id: UUID
    task_type: str
    status: TaskStatus
    progress: int
    current_step: str | None
    error_message: str | None
    total_cost_rmb: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    report_id: UUID | None = None
    steps: list[AgentStepView] = Field(default_factory=list)


class CodeEvidenceView(APIModel):
    citation_id: str | None = None
    provenance: Literal["portfolio", "reference"] = "portfolio"
    context_complete: bool = False
    context_note: str = "历史引用未核验上下文完整性"
    function_line_start: int | None = None
    function_line_end: int | None = None
    source_line_count: int | None = None
    skill: str
    evidence_type: str
    file_path: str
    line_start: int
    line_end: int
    snippet: Annotated[str, StringConstraints(strip_whitespace=False)]
    strength: str
    explanation: str
    content_hash: str
    project_file_id: UUID | None = None
    project_version_id: UUID | None = None
    source_id: UUID | None = None


class MatchItemView(APIModel):
    evidence_level_source: str = "rules"
    skill_path: list[str] = Field(default_factory=list)
    rating_criteria: list[dict] = Field(default_factory=list)
    evidence_level: int | None = Field(default=None, ge=1, le=5)
    evidence_level_label: str = "待评估"
    evidence_level_reason: str = ""
    evidence_level_gap: str = ""
    evidence_level_version: str = "practice-evidence-v2"
    requirement_id: UUID
    requirement_title: str
    skill: str
    claimed: bool
    claim_text: str | None
    evidence: CodeEvidenceView | None
    evidence_list: list[CodeEvidenceView]
    verdict: str
    ai_confidence: float | None
    rule_base_score: float
    weight: int
    final_score: float | None
    explanation: str
    formula_version: str
    evidence_id: UUID | None = None
    confirmation_status: ConfirmationStatus | None = None
    confirmed_at: datetime | None = None
    reviewer_note: str | None = None
    ai_explanation: str | None = None
    ai_citation_ids: list[str] = Field(default_factory=list)
    ai_information_gap: str | None = None
    ai_suggestion: str | None = None
    ai_task_plan: CareerTaskPlan | None = None
    ai_task_plan_warning: str | None = None
    ai_suggestion_redundant: bool = False
    ai_status: str = "not_used"
    ai_origin: str | None = None
    function_source_coverage: list[dict] = Field(default_factory=list)
    file_source_coverage: list[dict] = Field(default_factory=list)


class EvidenceReviewUpdate(APIModel):
    status: ConfirmationStatus
    note: str | None = Field(default=None, max_length=1000)


class MatchReportSummary(APIModel):
    id: UUID
    task_id: UUID
    job_id: UUID
    job_title: str
    job_category: str
    candidate_id: str
    candidate_name: str
    overall_score: float | None
    summary: str
    analysis_mode: str = "rules"
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_fallback_used: bool = False
    evidence_context_version: str | None = None
    created_at: datetime


class MatchReportHistorySummary(MatchReportSummary):
    """List-only facts; do not add new fields to old application snapshots."""

    materials: list[ReportMaterial] = Field(default_factory=list)
    job_report_count: int
    is_latest_for_job: bool


class EvidenceActionView(APIModel):
    requirement_id: UUID
    requirement_title: str
    skill: str
    weight: int
    current_level: int | None = None
    source: Literal["ai_suggestion", "rules", "review"]
    evidence_gap: str
    action: str
    citation_ids: list[str] = Field(default_factory=list)


class MatchReportView(MatchReportSummary):
    visual_claims: list[VisualReviewView] = Field(default_factory=list)
    materials: list[ReportMaterial] = Field(default_factory=list)
    gaps: list[str]
    claimed_only: list[str]
    items: list[MatchItemView]
    ai_usage: dict | None = None
    ai_tool_calls: list[dict] = Field(default_factory=list)
    ai_process: dict[str, str | None] = Field(default_factory=dict)
    action_plan: list[EvidenceActionView] = Field(default_factory=list)
