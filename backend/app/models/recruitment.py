from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class Skill(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SkillAlias(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "skill_aliases"

    skill_id: Mapped[UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class Job(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "jobs"
    __table_args__ = (CheckConstraint(
        "status IN ('draft', 'published', 'closed')", name="ck_jobs_status"),)

    enterprise_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("enterprises.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200), index=True)
    company_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    category: Mapped[str] = mapped_column(String(50), default="software", index=True)
    city: Mapped[str] = mapped_column(String(100), default="不限", index=True)
    employment_type: Mapped[str] = mapped_column(String(30), default="campus", index=True)


class JobRequirement(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "job_requirements"
    __table_args__ = (CheckConstraint(
        "normalized_status IN ('pending', 'normalized')",
        name="ck_job_requirements_normalized_status"),)

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), nullable=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    skill_name: Mapped[str] = mapped_column(String(100), index=True)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    normalized_status: Mapped[str] = mapped_column(String(30), default="pending")
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Application(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "applications"
    __table_args__ = (Index(
        "uq_applications_active_job_student", "job_id", "student_id", unique=True,
        postgresql_where=text("status != 'withdrawn'"),
        sqlite_where=text("status != 'withdrawn'"),
    ),
        CheckConstraint(
            "status IN ('submitted', 'viewed', 'downloaded', 'replied', 'withdrawn')",
            name="ck_applications_status"),
        CheckConstraint(
            "reply_kind IS NULL OR reply_kind IN ('interview', 'continue', 'declined')",
            name="ck_applications_reply_kind"),
        Index("ix_applications_student_created", "student_id", "created_at"),
        Index("ix_applications_job_created", "job_id", "created_at"),
    )

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    report_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("match_reports.id", ondelete="RESTRICT"), nullable=True
    )
    report_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    consent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_references: Mapped[list] = mapped_column(JSON, default=list)


class ApplicationEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "application_events"
    __table_args__ = (UniqueConstraint("application_id", "event_type"),)

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    event_type: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(Text, default="")
