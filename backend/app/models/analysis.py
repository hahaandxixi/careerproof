from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin
from app.models.enums import ConfirmationStatus, TaskStatus, VerificationStatus


class AnalysisTask(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "analysis_tasks"
    __table_args__ = (Index("ix_analysis_tasks_owner_type_status_created",
                            "created_by", "task_type", "status", "created_at"),)

    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    task_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), default=TaskStatus.PENDING, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_cost_rmb: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    run_token: Mapped[UUID | None] = mapped_column(nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentStep(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("analysis_task_id", "step_number"),)

    analysis_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), index=True
    )
    step_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class EvidenceSource(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "evidence_sources"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(resume_section_id, project_file_id, interview_answer_id) = 1",
            name="ck_evidence_source_exactly_one_reference",
        ),
    )

    resume_section_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resume_sections.id", ondelete="CASCADE"), nullable=True
    )
    project_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("project_files.id", ondelete="CASCADE"), nullable=True
    )
    interview_answer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interview_answers.id", ondelete="CASCADE"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    locator: Mapped[dict] = mapped_column(JSON, default=dict)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    source_version: Mapped[int] = mapped_column(Integer, default=1)


class SkillEvidence(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "skill_evidence"
    __table_args__ = (UniqueConstraint("analysis_task_id", "skill_id", "evidence_source_id"),)

    analysis_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), index=True
    )
    skill_id: Mapped[UUID] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"))
    evidence_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_sources.id", ondelete="CASCADE")
    )
    confidence: Mapped[float] = mapped_column(Float)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status")
    )
    confirmation_status: Mapped[ConfirmationStatus] = mapped_column(
        Enum(ConfirmationStatus, name="confirmation_status"),
        default=ConfirmationStatus.PENDING,
    )
    confirmed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class MatchingFormulaVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "matching_formula_versions"

    name: Mapped[str] = mapped_column(String(100))
    version_name: Mapped[str] = mapped_column(String(50), unique=True)
    configuration: Mapped[dict] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text, default="")


class MatchReport(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "match_reports"
    __table_args__ = (Index("ix_match_reports_job_candidate_created",
                            "job_id", "candidate_ref", "created_at"),)

    analysis_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), unique=True
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    candidate_ref: Mapped[str] = mapped_column(String(100), index=True)
    formula_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("matching_formula_versions.id", ondelete="SET NULL"), nullable=True
    )
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_name: Mapped[str] = mapped_column(String(100), default="")
    job_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    materials_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    analysis_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text)
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    claimed_only: Mapped[list] = mapped_column(JSON, default=list)


class MatchItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "match_items"
    __table_args__ = (
        CheckConstraint("verdict IN ('supported', 'partial', 'claimed_only', 'gap', 'unsupported')",
                        name="ck_match_items_verdict"),
        UniqueConstraint("report_id", "requirement_id", name="uq_match_items_report_requirement"),
    )

    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("match_reports.id", ondelete="CASCADE"), index=True
    )
    requirement_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_requirements.id", ondelete="CASCADE")
    )
    evidence_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("skill_evidence.id", ondelete="SET NULL"), nullable=True
    )
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rule_base_score: Mapped[float] = mapped_column(Float)
    weight: Mapped[int] = mapped_column(Integer)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    verdict: Mapped[str] = mapped_column(String(30))
    explanation: Mapped[str] = mapped_column(Text)
    formula_version: Mapped[str] = mapped_column(String(50))
    evidence_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AiUsageLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (
        # Idempotency key for one real model request within one claim of a task:
        # legacy rows have NULL run_token and stay exempt from the constraint.
        Index(
            "uq_ai_usage_logs_run_token_request_seq",
            "run_token",
            "request_seq",
            unique=True,
            sqlite_where=text("run_token IS NOT NULL"),
            postgresql_where=text("run_token IS NOT NULL"),
        ),
        # One ledger row per model request attempt; NULL keeps legacy rows exempt,
        # and both SQLite and PostgreSQL allow duplicated NULLs in a unique index.
        Index("uq_ai_usage_logs_attempt_id", "attempt_id", unique=True),
    )

    analysis_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit_tokens: Mapped[int] = mapped_column(Integer, default=0)
    unit_price_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_rmb: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    run_token: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    request_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "ai_request_attempts.id", ondelete="RESTRICT", name="fk_ai_usage_logs_attempt_id"
        ),
        nullable=True,
    )


class KnowledgeChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_id: Mapped[UUID] = mapped_column(index=True)
    content: Mapped[str] = mapped_column(Text)
    chunk_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
