"""Persist each physical model request attempt for the OPS-01B verification protocol.

Every real model call inside a run gets one ai_request_attempts row keyed by
(run_token, physical_sequence), with its own send/receipt/book lifecycle state.
The usage ledger gains a nullable attempt_id link; legacy ledger rows keep NULL
and stay exempt from the new unique index. Downgrade refuses to drop the table
while any attempt is still unsettled, so no in-flight or unbooked fact can be
silently destroyed.
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_ai_request_attempts"
down_revision = "0015_growth_answer_drafts"
branch_labels = None
depends_on = None

ATTEMPT_TABLE = "ai_request_attempts"
LEDGER_TABLE = "ai_usage_logs"
LEDGER_FK = "fk_ai_usage_logs_attempt_id"
LEDGER_INDEX = "uq_ai_usage_logs_attempt_id"

# Settled means either usage was booked or the attempt definitively never sent.
SETTLED_CONDITION = (
    "state = 'booked' OR (state = 'not_sent' AND ended_at IS NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        ATTEMPT_TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "analysis_task_id",
            sa.Uuid(),
            sa.ForeignKey("analysis_tasks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("run_token", sa.Uuid(), nullable=False),
        sa.Column("step", sa.String(length=64), nullable=False),
        sa.Column("physical_sequence", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="not_sent"),
        sa.Column("sending_day", sa.Date(), nullable=True),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("usage_input_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_output_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_cache_hit_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("usage_raw", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("response_digest", sa.String(length=64), nullable=True),
        sa.Column("send_intent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_token", "physical_sequence",
            name="uq_ai_request_attempts_run_token_physical_sequence",
        ),
        sa.CheckConstraint(
            "state IN ('not_sent', 'in_flight', 'received_unbooked', 'booked', 'usage_unknown')",
            name="ck_ai_request_attempts_state",
        ),
        sa.CheckConstraint(
            "physical_sequence > 0", name="ck_ai_request_attempts_physical_sequence_positive"
        ),
        sa.CheckConstraint(
            "estimated_input_tokens >= 0",
            name="ck_ai_request_attempts_estimated_input_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "max_output_tokens >= 0",
            name="ck_ai_request_attempts_max_output_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "usage_input_tokens IS NULL OR usage_input_tokens >= 0",
            name="ck_ai_request_attempts_usage_input_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "usage_output_tokens IS NULL OR usage_output_tokens >= 0",
            name="ck_ai_request_attempts_usage_output_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "usage_cache_hit_tokens IS NULL OR usage_cache_hit_tokens >= 0",
            name="ck_ai_request_attempts_usage_cache_hit_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_ai_request_attempts_latency_ms_non_negative",
        ),
    )
    # SQLite cannot ALTER a named FK into place, so the ledger link goes through
    # batch mode: a plain add/drop on SQLite, a table copy that keeps every
    # reflected constraint and the partial legacy index on SQLite, and a normal
    # ALTER on other dialects.
    with op.batch_alter_table(LEDGER_TABLE) as batch:
        batch.add_column(
            sa.Column(
                "attempt_id",
                sa.Uuid(),
                sa.ForeignKey(f"{ATTEMPT_TABLE}.id", ondelete="RESTRICT", name=LEDGER_FK),
                nullable=True,
            )
        )
    op.create_index(LEDGER_INDEX, LEDGER_TABLE, ["attempt_id"], unique=True)


def downgrade() -> None:
    connection = op.get_bind()
    unsettled = connection.execute(
        sa.text(
            f"SELECT state, COUNT(*) FROM {ATTEMPT_TABLE} "
            f"WHERE NOT ({SETTLED_CONDITION}) GROUP BY state"
        )
    ).fetchall()
    if unsettled:
        summary = ", ".join(f"{state}={count}" for state, count in unsettled)
        raise RuntimeError(
            "Refusing 0016 downgrade: ai_request_attempts still holds unsettled rows "
            f"({summary}). Only booked rows and not_sent rows with a non-empty ended_at "
            "are settled; resolve or book them before downgrading."
        )
    op.drop_index(LEDGER_INDEX, table_name=LEDGER_TABLE)
    with op.batch_alter_table(LEDGER_TABLE) as batch:
        batch.drop_column("attempt_id")
    op.drop_table(ATTEMPT_TABLE)
