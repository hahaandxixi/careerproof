"""Persistent admission capacity; these rows are not provider usage receipts."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
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


class AiDailyBudget(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_daily_budgets"
    __table_args__ = (
        UniqueConstraint("created_by", "budget_day", name="uq_ai_daily_budgets_owner_day"),
        CheckConstraint("policy_version > 0", name="ck_ai_daily_budgets_policy_positive"),
    )

    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    budget_day: Mapped[date] = mapped_column(Date, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class AiBudgetReservation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_budget_reservations"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_ai_budget_reservations_attempt"),
        CheckConstraint(
            "state IN ('held', 'settled', 'released', 'adjusted')",
            name="ck_ai_budget_reservations_state",
        ),
        CheckConstraint(
            "source IN ('admission', 'pre_budget_attempt')",
            name="ck_ai_budget_reservations_source",
        ),
        CheckConstraint(
            "input_bound >= 0 AND output_bound >= 0",
            name="ck_ai_budget_reservations_bounds",
        ),
        CheckConstraint(
            "(state = 'settled' AND actual_input_tokens IS NOT NULL "
            "AND actual_output_tokens IS NOT NULL AND actual_input_tokens >= 0 "
            "AND actual_output_tokens >= 0 AND settled_at IS NOT NULL) "
            "OR (state <> 'settled' AND actual_input_tokens IS NULL "
            "AND actual_output_tokens IS NULL AND settled_at IS NULL)",
            name="ck_ai_budget_reservations_actual_receipt_state",
        ),
        CheckConstraint(
            "(state = 'adjusted' AND adjusted_input_tokens IS NOT NULL "
            "AND adjusted_output_tokens IS NOT NULL AND adjusted_input_tokens >= 0 "
            "AND adjusted_output_tokens >= 0) OR (state <> 'adjusted' "
            "AND adjusted_input_tokens IS NULL AND adjusted_output_tokens IS NULL)",
            name="ck_ai_budget_reservations_adjustment_state",
        ),
    )

    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_request_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    analysis_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_token: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reservation_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    input_bound: Mapped[int] = mapped_column(Integer, nullable=False)
    output_bound: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="held", server_default="held")
    source: Mapped[str] = mapped_column(String(32), default="admission", server_default="admission")
    actual_input_tokens: Mapped[int | None] = mapped_column(Integer)
    actual_output_tokens: Mapped[int | None] = mapped_column(Integer)
    adjusted_input_tokens: Mapped[int | None] = mapped_column(Integer)
    adjusted_output_tokens: Mapped[int | None] = mapped_column(Integer)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiBudgetAdjustment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_budget_adjustments"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_ai_budget_adjustments_operation"),
        CheckConstraint("length(trim(reason)) > 0", name="ck_ai_budget_adjustments_reason"),
        CheckConstraint(
            "before_input_tokens >= 0 AND before_output_tokens >= 0 "
            "AND after_input_tokens >= 0 AND after_output_tokens >= 0",
            name="ck_ai_budget_adjustments_nonnegative",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    reservation_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_budget_reservations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    before_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    before_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    after_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    after_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)


class AiBudgetCutover(Base, TimestampMixin):
    """Shared activation gate; absent/disabled must reject budgeted external sends."""

    __tablename__ = "ai_budget_cutover"
    __table_args__ = (
        CheckConstraint("id = 'shared_daily_v1'", name="ck_ai_budget_cutover_singleton"),
        CheckConstraint(
            "NOT enabled OR (inventory_digest IS NOT NULL AND activated_at IS NOT NULL "
            "AND activated_by IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_ai_budget_cutover_activation_evidence",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inventory_digest: Mapped[str | None] = mapped_column(String(64))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(String(1000), default="", server_default="")
