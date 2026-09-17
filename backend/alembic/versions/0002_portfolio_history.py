"""Persist upload history links and idempotency keys without changing existing records."""

import sqlalchemy as sa

from alembic import op

revision = "0002_portfolio_history"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("create_request_id", sa.Uuid(), nullable=True))
    op.add_column("projects", sa.Column("create_request_hash", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_project_create_request", "projects", ["student_id", "create_request_id"]
    )
    for table in ("resume_versions", "project_versions"):
        op.add_column(table, sa.Column("original_filename", sa.String(255), nullable=True))
        op.add_column(table, sa.Column("analysis_task_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_analysis_task",
            table,
            "analysis_tasks",
            ["analysis_task_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.add_column("project_versions", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("project_versions", sa.Column("upload_request_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_project_upload_request", "project_versions", ["project_id", "upload_request_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_project_upload_request", "project_versions", type_="unique")
    op.drop_column("project_versions", "upload_request_id")
    op.drop_column("project_versions", "size_bytes")
    for table in ("resume_versions", "project_versions"):
        op.drop_constraint(f"fk_{table}_analysis_task", table, type_="foreignkey")
        op.drop_column(table, "analysis_task_id")
        op.drop_column(table, "original_filename")
    op.drop_constraint("uq_project_create_request", "projects", type_="unique")
    op.drop_column("projects", "create_request_hash")
    op.drop_column("projects", "create_request_id")
