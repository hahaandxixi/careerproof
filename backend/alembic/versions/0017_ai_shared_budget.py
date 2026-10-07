"""Persistent shared budget schema; activation remains disabled until audited cutover."""

import sqlalchemy as sa

from alembic import op

revision = "0017_ai_shared_budget"
down_revision = "0016_ai_request_attempts"
branch_labels = None
depends_on = None

TABLES = (
    "ai_daily_budgets",
    "ai_budget_reservations",
    "ai_budget_adjustments",
    "ai_budget_cutover",
)


def upgrade() -> None:
    op.create_table(
        "ai_daily_budgets",
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("budget_day", sa.Date(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "policy_version > 0",
            name="ck_ai_daily_budgets_policy_positive",
        ),
        sa.UniqueConstraint("created_by", "budget_day", name="uq_ai_daily_budgets_owner_day"),
    )
    op.create_table(
        "ai_budget_reservations",
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("ai_request_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "analysis_task_id",
            sa.Uuid(),
            sa.ForeignKey("analysis_tasks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("run_token", sa.Uuid(), nullable=False),
        sa.Column("reservation_day", sa.Date(), nullable=False),
        sa.Column("input_bound", sa.Integer(), nullable=False),
        sa.Column("output_bound", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="held"),
        sa.Column("source", sa.String(32), nullable=False, server_default="admission"),
        sa.Column("actual_input_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_output_tokens", sa.Integer(), nullable=True),
        sa.Column("adjusted_input_tokens", sa.Integer(), nullable=True),
        sa.Column("adjusted_output_tokens", sa.Integer(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(state = 'settled' AND actual_input_tokens IS NOT NULL AND "
            "actual_output_tokens IS NOT NULL AND actual_input_tokens >= 0 AND "
            "actual_output_tokens >= 0 AND settled_at IS NOT NULL) OR (state <> "
            "'settled' AND actual_input_tokens IS NULL AND actual_output_tokens IS NULL"
            " AND settled_at IS NULL)",
            name="ck_ai_budget_reservations_actual_receipt_state",
        ),
        sa.CheckConstraint(
            "(state = 'adjusted' AND adjusted_input_tokens IS NOT NULL AND "
            "adjusted_output_tokens IS NOT NULL AND adjusted_input_tokens >= 0 AND "
            "adjusted_output_tokens >= 0) OR (state <> 'adjusted' AND "
            "adjusted_input_tokens IS NULL AND adjusted_output_tokens IS NULL)",
            name="ck_ai_budget_reservations_adjustment_state",
        ),
        sa.CheckConstraint(
            "input_bound >= 0 AND output_bound >= 0",
            name="ck_ai_budget_reservations_bounds",
        ),
        sa.CheckConstraint(
            "source IN ('admission', 'pre_budget_attempt')",
            name="ck_ai_budget_reservations_source",
        ),
        sa.CheckConstraint(
            "state IN ('held', 'settled', 'released', 'adjusted')",
            name="ck_ai_budget_reservations_state",
        ),
        sa.UniqueConstraint("attempt_id", name="uq_ai_budget_reservations_attempt"),
    )
    op.create_index(
        "ix_ai_budget_reservations_reservation_day",
        "ai_budget_reservations",
        ["reservation_day"],
        unique=False,
    )
    op.create_table(
        "ai_budget_adjustments",
        sa.Column("operation_id", sa.String(100), nullable=False),
        sa.Column(
            "reservation_id",
            sa.Uuid(),
            sa.ForeignKey("ai_budget_reservations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("before_input_tokens", sa.Integer(), nullable=False),
        sa.Column("before_output_tokens", sa.Integer(), nullable=False),
        sa.Column("after_input_tokens", sa.Integer(), nullable=False),
        sa.Column("after_output_tokens", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "before_input_tokens >= 0 AND before_output_tokens >= 0 AND "
            "after_input_tokens >= 0 AND after_output_tokens >= 0",
            name="ck_ai_budget_adjustments_nonnegative",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0",
            name="ck_ai_budget_adjustments_reason",
        ),
        sa.UniqueConstraint("operation_id", name="uq_ai_budget_adjustments_operation"),
    )
    op.create_table(
        "ai_budget_cutover",
        sa.Column("id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("inventory_digest", sa.String(64), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "activated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "NOT enabled OR (inventory_digest IS NOT NULL AND activated_at IS NOT NULL "
            "AND activated_by IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_ai_budget_cutover_activation_evidence",
        ),
        sa.CheckConstraint(
            "id = 'shared_daily_v1'",
            name="ck_ai_budget_cutover_singleton",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    # Even settled capacity and activation evidence are audit facts; require an
    # explicit export/remediation outside this migration before any data loss.
    for name in TABLES:
        if connection.execute(sa.text(f"SELECT COUNT(*) FROM {name}")).scalar_one():
            raise RuntimeError(f"Refusing 0017 downgrade: persistent budget data remains in {name}")
    op.drop_table("ai_budget_cutover")
    op.drop_table("ai_budget_adjustments")
    op.drop_index("ix_ai_budget_reservations_reservation_day", table_name="ai_budget_reservations")
    op.drop_table("ai_budget_reservations")
    op.drop_table("ai_daily_budgets")
