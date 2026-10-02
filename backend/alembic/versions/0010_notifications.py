"""Transactional application event notifications; no historical backfill."""

import sqlalchemy as sa

from alembic import op

revision = "0010_notifications"
down_revision = "0009_evidence_growth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("application_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "recipient_id"),
    )
    op.create_index(
        "ix_notifications_recipient_created", "notifications", ["recipient_id", "created_at"]
    )


def downgrade():
    op.drop_table("notifications")
