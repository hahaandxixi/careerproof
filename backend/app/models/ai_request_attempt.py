"""One physical model request inside a verification run, for OPS-01B bookkeeping."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class AiRequestAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_request_attempts"
    __table_args__ = (
        UniqueConstraint(
            "run_token", "physical_sequence",
            name="uq_ai_request_attempts_run_token_physical_sequence",
        ),
        CheckConstraint(
            "state IN ('not_sent', 'in_flight', 'received_unbooked', 'booked', 'usage_unknown')",
            name="ck_ai_request_attempts_state",
        ),
        CheckConstraint(
            "physical_sequence > 0", name="ck_ai_request_attempts_physical_sequence_positive"
        ),
        CheckConstraint(
            "estimated_input_tokens >= 0",
            name="ck_ai_request_attempts_estimated_input_tokens_non_negative",
        ),
        CheckConstraint(
            "max_output_tokens >= 0",
            name="ck_ai_request_attempts_max_output_tokens_non_negative",
        ),
        CheckConstraint(
            "usage_input_tokens IS NULL OR usage_input_tokens >= 0",
            name="ck_ai_request_attempts_usage_input_tokens_non_negative",
        ),
        CheckConstraint(
            "usage_output_tokens IS NULL OR usage_output_tokens >= 0",
            name="ck_ai_request_attempts_usage_output_tokens_non_negative",
        ),
        CheckConstraint(
            "usage_cache_hit_tokens IS NULL OR usage_cache_hit_tokens >= 0",
            name="ck_ai_request_attempts_usage_cache_hit_tokens_non_negative",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_ai_request_attempts_latency_ms_non_negative",
        ),
    )

    analysis_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_token: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    physical_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_sent", server_default="not_sent"
    )
    sending_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    usage_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_cache_hit_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_raw: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    response_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    send_intent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    receipt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
