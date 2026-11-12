from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class InterviewSessionSummary(APIModel):
    id: UUID
    job_id: UUID
    job_title: str | None
    requirement_title: str | None
    skill: str | None
    status: str
    needs_attention: bool
    updated_at: datetime


class InterviewSessionCreate(APIModel):
    requirement_id: UUID
    restart: bool = False


class InterviewStartRequest(APIModel):
    external_ai_consent: bool


class InterviewAnswerRequest(APIModel):
    answer_text: str = Field(min_length=1, max_length=4000)
    # The client keeps this value while retrying the same submitted answer.
    client_token: str = Field(min_length=8, max_length=80)


class PracticeEvidenceView(APIModel):
    citation_id: str
    file_path: str
    line_start: int
    line_end: int
    snippet: str
    content_hash: str = ""
    provenance: str = "portfolio"
    project_version_id: str | None = None


class PracticeKnowledgeView(APIModel):
    knowledge_id: str
    title: str
    skill: str = ""
    document: str = ""
    section: str = ""
    source_locator: str = ""
    source_label: str = ""
    source_version: str = ""
    review_status: str = ""
    reviewed_at: str = ""


class PracticeConflictView(APIModel):
    answer_quote: str
    reason: str
    basis_id: str


class PracticeFeedbackView(APIModel):
    covered: list[str] = Field(default_factory=list)
    inconsistent: list[str] = Field(default_factory=list)
    conflict_details: list[PracticeConflictView] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    review_suggestion: str = ""
    citations: list[PracticeEvidenceView] = Field(default_factory=list)
    knowledge: list[PracticeKnowledgeView] = Field(default_factory=list)


class PracticeGenerationView(APIModel):
    id: UUID
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    error_message: str | None = None


class ResolvedPracticeIssue(APIModel):
    issue_id: str
    kind: Literal["missing", "inconsistent"]
    text: str
    answer_quote: str
    turn_index: int


class PracticeTurnView(APIModel):
    turn_index: int
    kind: Literal["first", "follow_up"] = "first"
    question: str
    focus: str = ""
    state: Literal["question", "answered", "feedback", "failed"]
    answer_text: str | None = None
    answered_at: datetime | None = None
    failure_reason: str | None = None
    citations: list[PracticeEvidenceView] = Field(default_factory=list)
    knowledge: list[PracticeKnowledgeView] = Field(default_factory=list)
    feedback: PracticeFeedbackView | None = None
    feedback_task: PracticeGenerationView | None = None


class PracticeSummaryView(APIModel):
    answered_turns: int = 0
    covered: list[str] = Field(default_factory=list)
    inconsistent: list[str] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    resolved_issues: list[ResolvedPracticeIssue] = Field(default_factory=list)
    next_step: str = ""
    note: str = ""


class InterviewSessionView(APIModel):
    id: UUID
    status: Literal["draft", "in_progress", "completed"]
    report_id: UUID
    job_id: UUID
    requirement_id: UUID
    requirement_title: str
    skill: str
    job_title: str
    materials: list[dict] = Field(default_factory=list)
    evidence: list[PracticeEvidenceView] = Field(default_factory=list)
    knowledge: list[PracticeKnowledgeView] = Field(default_factory=list)
    knowledge_outdated: bool = False
    consent_at: datetime | None = None
    consent_scope: str | None = None
    current_turn: int
    max_turns: int
    summary: PracticeSummaryView | None = None
    question_task: PracticeGenerationView | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    turns: list[PracticeTurnView] = Field(default_factory=list)


class InterviewSessionEnvelope(APIModel):
    session: InterviewSessionView
    resumed: bool = False
