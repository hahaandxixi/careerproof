"""Bind a student's evidence gap to selected versions and a follow-up report."""

import sqlalchemy as sa

from alembic import op

revision = "0009_evidence_growth"
down_revision = "0008_application_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_growth_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "base_report_id",
            sa.Uuid(),
            sa.ForeignKey("match_reports.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("base_snapshot", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("materials", sa.JSON(), nullable=False),
        sa.Column(
            "analysis_task_id",
            sa.Uuid(),
            sa.ForeignKey("analysis_tasks.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("created_by", "base_report_id", "requirement_id"),
    )
    op.create_index("ix_evidence_growth_tasks_created_by", "evidence_growth_tasks", ["created_by"])


def downgrade():
    op.drop_table("evidence_growth_tasks")
