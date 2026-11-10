"""Curated technical knowledge used as interview practice grounding.

One row per technical card. ``reference_points`` stay server-side: they seed
feedback, never the pre-answer view. Material chunks remain in ``knowledge_chunks``
with owner-scoped source ids; this table is the separate technical scope.
"""

from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class TechnicalKnowledgeEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "technical_knowledge_entries"

    knowledge_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    skill: Mapped[str] = mapped_column(String(100), index=True)
    topic: Mapped[str] = mapped_column(String(60), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    principle: Mapped[str] = mapped_column(Text, default="")
    reference_points: Mapped[list] = mapped_column(JSON, default=list)
    question_angles: Mapped[list] = mapped_column(JSON, default=list)
    document: Mapped[str] = mapped_column(String(300), default="")
    section: Mapped[str] = mapped_column(String(200), default="")
    source_locator: Mapped[str] = mapped_column(String(300), default="")
    source_label: Mapped[str] = mapped_column(String(300), default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    source_version: Mapped[str] = mapped_column(String(80), default="")
    review_status: Mapped[str] = mapped_column(String(30), default="needs_recheck")
    reviewed_at: Mapped[str] = mapped_column(String(40), default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
