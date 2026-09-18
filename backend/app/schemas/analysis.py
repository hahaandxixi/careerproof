from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.enums import ConfirmationStatus, TaskStatus
from app.schemas.common import APIModel


class MatchCreate(APIModel):
    job_id: UUID
    resume_version_id: UUID
    project_version_ids: list[UUID] = Field(default_factory=list, max_length=10)
    external_ai_consent: bool = False


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
    context_complete: bool = False
    context_note: str = "历史引用未核验上下文完整性"
    skill: str
    evidence_type: str
    file_path: str
    line_start: int
    line_end: int
    snippet: str
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
    ai_status: str = "not_used"
    ai_origin: str | None = None


class EvidenceReviewUpdate(APIModel):
    status: ConfirmationStatus
    note: str | None = Field(default=None, max_length=1000)


class DeepSeekWebHandoff(APIModel):
    provider_url: str
    prompt: str
    prompt_version: str
    privacy_notice: str
    requirement_count: int
    context_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class DeepSeekWebImport(APIModel):
    response: dict
    context_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReportMaterial(APIModel):
    kind: str
    id: UUID
    title: str
    version_number: int
    content_hash: str


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


class MatchReportView(MatchReportSummary):
    materials: list[ReportMaterial] = Field(default_factory=list)
    gaps: list[str]
    claimed_only: list[str]
    items: list[MatchItemView]
    ai_usage: dict | None = None
    ai_tool_calls: list[dict] = Field(default_factory=list)
