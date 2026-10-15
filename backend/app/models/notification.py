from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("event_id", "recipient_id"),
        Index("ix_notifications_recipient_created", "recipient_id", "created_at"),
        Index("ix_notifications_recipient_unread", "recipient_id",
              postgresql_where=text("read_at IS NULL"), sqlite_where=text("read_at IS NULL")),
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("application_events.id", ondelete="CASCADE"))
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
