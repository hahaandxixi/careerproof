from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class Resume(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "resumes"

    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class ResumeVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("resume_id", "version_number"),)

    resume_id: Mapped[UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    version_number: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    parse_status: Mapped[str] = mapped_column(String(30), default="pending")
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analysis_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"), nullable=True
    )


class ResumeSection(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "resume_sections"

    resume_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), index=True
    )
    section_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("student_id", "create_request_id", name="uq_project_create_request"),
    )

    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    create_request_id: Mapped[UUID | None] = mapped_column(nullable=True)
    create_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProjectVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "project_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_number"),
        UniqueConstraint("project_id", "upload_request_id", name="uq_project_upload_request"),
    )

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version_number: Mapped[int] = mapped_column(Integer)
    material_role: Mapped[str] = mapped_column(String(20), default="portfolio")
    archive_storage_key: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    analysis_status: Mapped[str] = mapped_column(String(30), default="pending")
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    upload_request_id: Mapped[UUID | None] = mapped_column(nullable=True)
    analysis_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"), nullable=True
    )


class ProjectFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "project_files"
    __table_args__ = (UniqueConstraint("project_version_id", "relative_path"),)

    project_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("project_versions.id", ondelete="CASCADE"), index=True
    )
    relative_path: Mapped[str] = mapped_column(String(1000))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    line_count: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(1000))
    analysis_status: Mapped[str] = mapped_column(String(30), default="pending")


class InterviewSession(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    """A text practice run bound to one saved report requirement.

    Legacy rows predate the practice fields; every new column is nullable so an
    old session is never rewritten or given invented report identity.
    """

    __tablename__ = "interview_sessions"

    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    report_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("match_reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requirement_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_requirements.id", ondelete="SET NULL"), nullable=True
    )
    requirement_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    skill: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    materials_snapshot: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    evidence_snapshot: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    knowledge_snapshot: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    question_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"), nullable=True
    )
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_scope: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_turn: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    max_turns: Mapped[int | None] = mapped_column(Integer, default=2, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InterviewAnswer(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    """One turn: the asked question and, once submitted, the student's answer."""

    __tablename__ = "interview_answers"
    __table_args__ = (
        # Legacy rows keep NULL turn indexes and stay outside both constraints.
        Index(
            "uq_interview_answers_session_turn",
            "session_id",
            "turn_index",
            unique=True,
            sqlite_where=text("turn_index IS NOT NULL"),
            postgresql_where=text("turn_index IS NOT NULL"),
        ),
        Index(
            "uq_interview_answers_session_client_token",
            "session_id",
            "client_token",
            unique=True,
            sqlite_where=text("client_token IS NOT NULL"),
            postgresql_where=text("client_token IS NOT NULL"),
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    answer_text: Mapped[str] = mapped_column(Text, default="")
    audio_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_focus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    basis_citation_ids: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    basis_knowledge_ids: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feedback_citation_ids: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    feedback_knowledge_ids: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    feedback_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"), nullable=True
    )
    client_token: Mapped[str | None] = mapped_column(String(80), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
