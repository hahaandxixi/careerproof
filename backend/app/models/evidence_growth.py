from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceGrowthTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "evidence_growth_tasks"
    __table_args__ = (UniqueConstraint("created_by", "base_report_id", "requirement_id"),)

    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    base_report_id: Mapped[UUID] = mapped_column(
        ForeignKey("match_reports.id", ondelete="RESTRICT")
    )
    requirement_id: Mapped[UUID] = mapped_column()
    base_snapshot: Mapped[dict] = mapped_column(JSON)
    plan: Mapped[dict] = mapped_column(JSON)
    materials: Mapped[list] = mapped_column(JSON, default=list)
    target_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", name="fk_evidence_growth_target_job", ondelete="RESTRICT"),
        nullable=True,
    )
    analysis_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="planned")
