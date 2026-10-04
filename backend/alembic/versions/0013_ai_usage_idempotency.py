"""Add the per-request idempotency key to ai_usage_logs.

B-08: usage must be booked in its own short transaction right after the model
responds, decoupled from the task lease/finalization outcome. Retries of the
same claim re-insert the same (run_token, request_seq) pair, so a partial
unique index makes the ledger write idempotent. Legacy rows keep NULL run_token
and are exempt from the constraint; nothing existing is rewritten.
"""

import sqlalchemy as sa

from alembic import op

revision = "0013_ai_usage_idempotency"
down_revision = "0012_knowledge_vec384"
branch_labels = None
depends_on = None

TABLE = "ai_usage_logs"
INDEX = "uq_ai_usage_logs_run_token_request_seq"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("run_token", sa.Uuid(), nullable=True))
    op.add_column(TABLE, sa.Column("request_seq", sa.Integer(), nullable=True))
    op.create_index(
        INDEX,
        TABLE,
        ["run_token", "request_seq"],
        unique=True,
        sqlite_where=sa.text("run_token IS NOT NULL"),
        postgresql_where=sa.text("run_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, "request_seq")
    op.drop_column(TABLE, "run_token")
