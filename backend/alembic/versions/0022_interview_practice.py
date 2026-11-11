"""Technical knowledge cards and the interview practice session fields.

All interview columns are nullable additions: existing sessions remain valid
records and are never given invented report identity. The curated cards are
inserted once by stable ``knowledge_id`` and are the single technical retrieval
source; nothing is loaded from a file index at request time.
"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.knowledge.technical_seed import TECHNICAL_KNOWLEDGE, content_digest

revision = "0022_interview_practice"
down_revision = "0021_job_discovery_flags"
branch_labels = None
depends_on = None


def _knowledge_table() -> sa.TableClause:
    return sa.table(
        "technical_knowledge_entries",
        sa.column("id", sa.Uuid),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("knowledge_id", sa.String),
        sa.column("title", sa.String),
        sa.column("skill", sa.String),
        sa.column("topic", sa.String),
        sa.column("summary", sa.Text),
        sa.column("principle", sa.Text),
        sa.column("reference_points", sa.JSON),
        sa.column("question_angles", sa.JSON),
        sa.column("document", sa.String),
        sa.column("section", sa.String),
        sa.column("source_locator", sa.String),
        sa.column("source_label", sa.String),
        sa.column("source_url", sa.String),
        sa.column("source_version", sa.String),
        sa.column("review_status", sa.String),
        sa.column("reviewed_at", sa.String),
        sa.column("content_hash", sa.String),
        sa.column("tags", sa.JSON),
    )


def upgrade():
    op.create_table(
        "technical_knowledge_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("knowledge_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("skill", sa.String(length=100), nullable=False),
        sa.Column("topic", sa.String(length=60), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("principle", sa.Text(), nullable=False),
        sa.Column("reference_points", sa.JSON(), nullable=False),
        sa.Column("question_angles", sa.JSON(), nullable=False),
        sa.Column("document", sa.String(length=300), nullable=False),
        sa.Column("section", sa.String(length=200), nullable=False),
        sa.Column("source_locator", sa.String(length=300), nullable=False),
        sa.Column("source_label", sa.String(length=300), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("reviewed_at", sa.String(length=40), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_technical_knowledge_entries_knowledge_id",
        "technical_knowledge_entries",
        ["knowledge_id"],
        unique=True,
    )
    op.create_index(
        "ix_technical_knowledge_entries_skill", "technical_knowledge_entries", ["skill"]
    )
    op.create_index(
        "ix_technical_knowledge_entries_topic", "technical_knowledge_entries", ["topic"]
    )
    op.create_index(
        "ix_technical_knowledge_entries_content_hash",
        "technical_knowledge_entries",
        ["content_hash"],
    )

    # Practice binding for a saved report requirement. Nullable by design, and
    # added through batch mode so SQLite rebuilds the table without losing the
    # legacy rows this project may already hold.
    with op.batch_alter_table("interview_sessions") as batch:
        batch.add_column(sa.Column("report_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("requirement_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("requirement_title", sa.Text(), nullable=True))
        batch.add_column(sa.Column("skill", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("job_title", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("materials_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("evidence_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("knowledge_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("consent_scope", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("current_turn", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("max_turns", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("summary", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("failure_reason", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_interview_sessions_report", "match_reports", ["report_id"], ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_interview_sessions_requirement", "job_requirements", ["requirement_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_interview_sessions_report_id", "interview_sessions", ["report_id"])

    with op.batch_alter_table("interview_answers") as batch:
        batch.add_column(sa.Column("turn_index", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("kind", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("question_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("question_focus", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("basis_citation_ids", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("basis_knowledge_ids", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("state", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("feedback", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("feedback_citation_ids", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("feedback_knowledge_ids", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("client_token", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("ai_model", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("failure_reason", sa.String(length=200), nullable=True))
    op.create_index(
        "uq_interview_answers_session_turn",
        "interview_answers",
        ["session_id", "turn_index"],
        unique=True,
        postgresql_where=sa.text("turn_index IS NOT NULL"),
        sqlite_where=sa.text("turn_index IS NOT NULL"),
    )
    op.create_index(
        "uq_interview_answers_session_client_token",
        "interview_answers",
        ["session_id", "client_token"],
        unique=True,
        postgresql_where=sa.text("client_token IS NOT NULL"),
        sqlite_where=sa.text("client_token IS NOT NULL"),
    )

    table = _knowledge_table()
    connection = op.get_bind()
    known = {
        row[0]
        for row in connection.execute(sa.select(table.c.knowledge_id))
    }
    now = datetime.now(UTC)
    for entry in TECHNICAL_KNOWLEDGE:
        if entry["knowledge_id"] in known:
            continue
        connection.execute(
            table.insert().values(
                id=uuid4(),
                created_at=now,
                updated_at=now,
                knowledge_id=entry["knowledge_id"],
                title=entry["title"],
                skill=entry["skill"],
                topic=entry["topic"],
                summary=entry["summary"],
                principle=entry["principle"],
                reference_points=entry["reference_points"],
                question_angles=entry["question_angles"],
                document=entry["document"],
                section=entry["section"],
                source_locator=entry["source_locator"],
                source_label=entry["source_label"],
                source_url=entry["source_url"],
                source_version=entry["source_version"],
                review_status=entry["review_status"],
                reviewed_at=entry["reviewed_at"],
                content_hash=content_digest(entry),
                tags=entry["tags"],
            )
        )


def downgrade():
    op.drop_index("uq_interview_answers_session_client_token", table_name="interview_answers")
    op.drop_index("uq_interview_answers_session_turn", table_name="interview_answers")
    with op.batch_alter_table("interview_answers") as batch:
        for name in (
            "turn_index",
            "kind",
            "question_text",
            "question_focus",
            "basis_citation_ids",
            "basis_knowledge_ids",
            "state",
            "feedback",
            "feedback_citation_ids",
            "feedback_knowledge_ids",
            "client_token",
            "answered_at",
            "feedback_at",
            "ai_model",
            "failure_reason",
        ):
            batch.drop_column(name)
    op.drop_index("ix_interview_sessions_report_id", table_name="interview_sessions")
    with op.batch_alter_table("interview_sessions") as batch:
        batch.drop_constraint("fk_interview_sessions_requirement", type_="foreignkey")
        batch.drop_constraint("fk_interview_sessions_report", type_="foreignkey")
        for name in (
            "report_id",
            "requirement_id",
            "requirement_title",
            "skill",
            "job_title",
            "materials_snapshot",
            "evidence_snapshot",
            "knowledge_snapshot",
            "consent_at",
            "consent_scope",
            "current_turn",
            "max_turns",
            "summary",
            "failure_reason",
            "completed_at",
        ):
            batch.drop_column(name)
    op.drop_index(
        "ix_technical_knowledge_entries_content_hash", table_name="technical_knowledge_entries"
    )
    op.drop_index("ix_technical_knowledge_entries_topic", table_name="technical_knowledge_entries")
    op.drop_index("ix_technical_knowledge_entries_skill", table_name="technical_knowledge_entries")
    op.drop_index(
        "ix_technical_knowledge_entries_knowledge_id", table_name="technical_knowledge_entries"
    )
    op.drop_table("technical_knowledge_entries")
