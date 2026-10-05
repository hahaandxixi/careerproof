"""Persist the student's explicitly selected private comparison target."""

import sqlalchemy as sa

from alembic import op

revision = "0014_growth_target_job"
down_revision = "0013_ai_usage_idempotency"
branch_labels = None
depends_on = None

TABLE = "evidence_growth_tasks"
CONSTRAINT = "fk_evidence_growth_target_job"


def upgrade():
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(sa.Column("target_job_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(CONSTRAINT, "jobs", ["target_job_id"], ["id"], ondelete="RESTRICT")


def downgrade():
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT, type_="foreignkey")
        batch.drop_column("target_job_id")
