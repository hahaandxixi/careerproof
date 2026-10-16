"""Persist short-lived login limits without changing account state."""

import sqlalchemy as sa

from alembic import op

revision = "0020_login_limits"
down_revision = "0019_data_integrity_constraints"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_limits",
        sa.Column("key_hash", sa.String(64), primary_key=True, nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("attempts > 0", name="ck_login_limits_positive_attempts"),
        sa.CheckConstraint("scope IN ('source', 'pair')", name="ck_login_limits_scope"),
    )
    op.create_index("ix_login_limits_expires_at", "login_limits", ["expires_at"])


def downgrade():
    op.drop_index("ix_login_limits_expires_at", table_name="login_limits")
    op.drop_table("login_limits")
