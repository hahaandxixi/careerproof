from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
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
    __table_args__ = (UniqueConstraint("job_id", "student_id"),)

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
