"""Keep human reply links bound to the submitted report's own evidence."""

import sqlalchemy as sa

from alembic import op

revision = "0011_reply_refs"
down_revision = "0010_notifications"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "applications",
        sa.Column(
            "reply_references", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
    )


def downgrade():
    op.drop_column("applications", "reply_references")
