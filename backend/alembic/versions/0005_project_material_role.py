"""Record whether an uploaded project version is a personal work or reference.

Revision ID: 0005_project_material_role
Revises: 0004_ai_evidence_analysis
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_project_material_role"
down_revision = "0004_ai_evidence_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_versions",
        sa.Column("material_role", sa.String(20), nullable=False, server_default="portfolio"),
    )
    op.alter_column("project_versions", "material_role", server_default=None)


def downgrade() -> None:
    op.drop_column("project_versions", "material_role")
