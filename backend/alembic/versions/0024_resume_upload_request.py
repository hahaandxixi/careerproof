"""Idempotent resume upload attempts; preserve existing resumes."""

import sqlalchemy as sa

from alembic import op

revision = "0024_resume_upload_request"
down_revision = "0023_interview_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resumes") as batch:
        batch.add_column(sa.Column("upload_request_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("upload_request_hash", sa.String(length=64), nullable=True))
        batch.create_unique_constraint(
            "uq_resume_upload_request", ["student_id", "upload_request_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("resumes") as batch:
        batch.drop_constraint("uq_resume_upload_request", type_="unique")
        batch.drop_column("upload_request_hash")
        batch.drop_column("upload_request_id")
