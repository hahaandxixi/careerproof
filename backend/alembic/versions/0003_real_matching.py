"""Persist job filters, recoverable tasks and immutable report inputs."""

import sqlalchemy as sa

from alembic import op

revision = "0003_real_matching"
down_revision = "0002_portfolio_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, length, default in (
        ("category", 50, "software"),
        ("city", 100, "不限"),
        ("employment_type", 30, "campus"),
    ):
        op.add_column(
            "jobs", sa.Column(name, sa.String(length), nullable=False, server_default=default)
        )
        op.alter_column("jobs", name, server_default=None)
        op.create_index(f"ix_jobs_{name}", "jobs", [name])
    op.add_column(
        "analysis_tasks", sa.Column("attempt", sa.Integer(), nullable=False, server_default="0")
    )
    op.alter_column("analysis_tasks", "attempt", server_default=None)
    op.add_column("analysis_tasks", sa.Column("run_token", sa.Uuid(), nullable=True))
    op.add_column("analysis_tasks", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column(
        "analysis_tasks",
        sa.Column("input_snapshot", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.alter_column("analysis_tasks", "input_snapshot", server_default=None)
    op.alter_column("match_reports", "overall_score", existing_type=sa.Float(), nullable=True)
    op.alter_column("match_items", "final_score", existing_type=sa.Float(), nullable=True)
    for name, kind, default in (
        ("candidate_name", sa.String(100), ""),
        ("job_snapshot", sa.JSON(), "{}"),
        ("materials_snapshot", sa.JSON(), "[]"),
    ):
        op.add_column(
            "match_reports", sa.Column(name, kind, nullable=False, server_default=default)
        )
        op.alter_column("match_reports", name, server_default=None)


def downgrade() -> None:
    # Scores without an applicable evaluator cannot be truthfully changed to zero.
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM match_reports WHERE overall_score IS NULL) "
            "OR EXISTS(SELECT 1 FROM match_items WHERE final_score IS NULL)"
        )
    ):
        raise RuntimeError("存在不可评分的报告，不能无损降级；请先备份并处理这些报告。")
    for name in ("materials_snapshot", "job_snapshot", "candidate_name"):
        op.drop_column("match_reports", name)
    op.alter_column("match_items", "final_score", existing_type=sa.Float(), nullable=False)
    op.alter_column("match_reports", "overall_score", existing_type=sa.Float(), nullable=False)
    for name in ("input_snapshot", "heartbeat_at", "run_token", "attempt"):
        op.drop_column("analysis_tasks", name)
    for name in ("employment_type", "city", "category"):
        op.drop_index(f"ix_jobs_{name}", table_name="jobs")
        op.drop_column("jobs", name)
