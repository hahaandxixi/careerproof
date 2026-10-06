"""Store the student's private answer draft for one evidence growth task."""

import sqlalchemy as sa

from alembic import op

revision = "0015_growth_answer_drafts"
down_revision = "0014_growth_target_job"
branch_labels = None
depends_on = None

TABLE = "growth_answer_drafts"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "growth_task_id",
            sa.Uuid(),
            sa.ForeignKey("evidence_growth_tasks.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("text", sa.String(length=6000), nullable=False),
        sa.Column("references", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table(TABLE)
