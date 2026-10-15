"""Reject invalid states and duplicate requirements; preserve consent history."""

import sqlalchemy as sa

from alembic import op

revision = "0019_data_integrity_constraints"
down_revision = "0018_application_reconsent"
branch_labels = None
depends_on = None

CHECKS = {
    "applications": {
        "status": "status IN ('submitted', 'viewed', 'downloaded', 'replied', 'withdrawn')",
        "reply_kind": "reply_kind IS NULL OR reply_kind IN ('interview', 'continue', 'declined')",
    },
    "jobs": {"status": "status IN ('draft', 'published', 'closed')"},
    "job_requirements": {"normalized_status": "normalized_status IN ('pending', 'normalized')"},
    "match_items": {
        "verdict": "verdict IN ('supported', 'partial', 'claimed_only', 'gap', 'unsupported')",
    },
}
INDEXES = [
    ("applications", "ix_applications_student_created", ["student_id", "created_at"]),
    ("applications", "ix_applications_job_created", ["job_id", "created_at"]),
    ("analysis_tasks", "ix_analysis_tasks_owner_type_status_created",
     ["created_by", "task_type", "status", "created_at"]),
    ("match_reports", "ix_match_reports_job_candidate_created",
     ["job_id", "candidate_ref", "created_at"]),
    ("notifications", "ix_notifications_recipient_unread", ["recipient_id"]),
]


def _check_sqlite_foreign_keys():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite" and bind.scalar(sa.text("PRAGMA foreign_keys")):
        raise RuntimeError("Disable SQLite foreign_keys before the migration transaction")


def _preflight():
    bind = op.get_bind()
    for table, checks in CHECKS.items():
        for column, expression in checks.items():
            invalid = bind.execute(sa.text(
                f"SELECT {column} FROM {table} WHERE NOT ({expression}) LIMIT 1"
            )).first()
            if invalid is not None:
                raise RuntimeError(f"Invalid {table}.{column}: {invalid[0]!r}; preserve history")
    if bind.scalar(sa.text("SELECT 1 FROM match_items GROUP BY report_id, requirement_id "
                           "HAVING COUNT(*) > 1 LIMIT 1")):
        raise RuntimeError("Duplicate match_items report/requirement; preserve history")


def upgrade():
    _check_sqlite_foreign_keys()
    _preflight()  # All validation precedes any schema mutation, including SQLite DDL.
    for table, checks in CHECKS.items():
        with op.batch_alter_table(table) as batch:
            for column, expression in checks.items():
                batch.create_check_constraint(f"ck_{table}_{column}", expression)
            if table == "match_items":
                batch.create_unique_constraint("uq_match_items_report_requirement",
                                               ["report_id", "requirement_id"])
    for table, name, columns in INDEXES:
        options = {}
        if table == "notifications":
            options = {"postgresql_where": sa.text("read_at IS NULL"),
                       "sqlite_where": sa.text("read_at IS NULL")}
        op.create_index(name, table, columns, **options)


def downgrade():
    _check_sqlite_foreign_keys()
    for table, name, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
    for table, checks in reversed(list(CHECKS.items())):
        with op.batch_alter_table(table) as batch:
            if table == "match_items":
                batch.drop_constraint("uq_match_items_report_requirement", type_="unique")
            for column in reversed(checks):
                batch.drop_constraint(f"ck_{table}_{column}", type_="check")
