from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class GrowthAnswerDraft(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The student's private answer draft; one per evidence growth task."""

    __tablename__ = "growth_answer_drafts"

    growth_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_growth_tasks.id", ondelete="CASCADE"), unique=True
    )
    text: Mapped[str] = mapped_column(String(6000), nullable=False, default="")
    references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
