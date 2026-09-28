"""Scope enterprise reads to explicit, revocable application consent."""

import sqlalchemy as sa

from alembic import op

revision = "0008_application_workflow"
down_revision = "0007_material_archiving"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("report_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_application_report",
        "applications",
        "match_reports",
        ["report_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "applications", sa.Column("report_snapshot", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column("applications", sa.Column("consent_version", sa.String(50), nullable=True))
    op.add_column(
        "applications", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("applications", sa.Column("reply_kind", sa.String(30), nullable=True))
    op.add_column("applications", sa.Column("reply_text", sa.Text(), nullable=True))
    op.create_table(
        "application_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("application_id", "event_type"),
    )
    op.create_index(
        "ix_application_events_application_id", "application_events", ["application_id"]
    )


def downgrade():
    op.drop_table("application_events")
    op.drop_constraint("fk_application_report", "applications", type_="foreignkey")
    for name in (
        "reply_text",
        "reply_kind",
        "consent_at",
        "consent_version",
        "report_snapshot",
        "report_id",
    ):
        op.drop_column("applications", name)
