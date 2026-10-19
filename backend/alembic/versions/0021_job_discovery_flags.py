"""Add explicit demo identity and discovery visibility to jobs.

Two additive columns only: nothing is inferred from titles and no existing row is
rewritten. Defaults keep every current enterprise posting real (is_demo=false) and
discoverable (discovery_visible=true), so applying this migration changes no behaviour
by itself. Curating the sample set is a separate, explicit import step.
"""

import sqlalchemy as sa

from alembic import op

revision = "0021_job_discovery_flags"
down_revision = "0020_login_limits"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "jobs",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "jobs",
        sa.Column("discovery_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_jobs_is_demo", "jobs", ["is_demo"])
    op.create_index("ix_jobs_discovery_visible", "jobs", ["discovery_visible"])


def downgrade():
    op.drop_index("ix_jobs_discovery_visible", table_name="jobs")
    op.drop_index("ix_jobs_is_demo", table_name="jobs")
    op.drop_column("jobs", "discovery_visible")
    op.drop_column("jobs", "is_demo")
