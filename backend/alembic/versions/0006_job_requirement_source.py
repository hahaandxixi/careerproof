"""Retain exact source spans for AI-assisted job requirement drafts.

Revision ID: 0006_job_requirement_source
Revises: 0005_project_material_role
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_job_requirement_source"
down_revision = "0005_project_material_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_requirements", sa.Column("source_quote", sa.Text(), nullable=True))
    op.add_column("job_requirements", sa.Column("source_start", sa.Integer(), nullable=True))
    op.add_column("job_requirements", sa.Column("source_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_requirements", "source_end")
    op.drop_column("job_requirements", "source_start")
    op.drop_column("job_requirements", "source_quote")
