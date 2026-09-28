"""Keep retired fixtures recoverable without crowding material selection."""

import sqlalchemy as sa

from alembic import op

revision = "0007_material_archiving"
down_revision = "0006_job_requirement_source"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("resumes", "projects"):
        op.add_column(
            table, sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade():
    for table in ("projects", "resumes"):
        op.drop_column(table, "is_archived")
