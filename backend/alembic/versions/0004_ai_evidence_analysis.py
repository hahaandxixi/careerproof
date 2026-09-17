"""Store report-level AI workflow metadata.

Revision ID: 0004_ai_evidence_analysis
Revises: 0003_real_matching
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_ai_evidence_analysis"
down_revision = "0003_real_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "match_reports",
        sa.Column("analysis_metadata", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.alter_column("match_reports", "analysis_metadata", server_default=None)


def downgrade() -> None:
    op.drop_column("match_reports", "analysis_metadata")
