"""Allow fresh consent after withdrawal, without reviving historical applications."""

import sqlalchemy as sa

from alembic import op

revision = "0018_application_reconsent"
down_revision = "0017_ai_shared_budget"
branch_labels = None
depends_on = None

TABLE = "applications"
INDEX = "uq_applications_active_job_student"
LEGACY = "uq_applications_job_id_student_id"
NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s"}


def _check_sqlite_foreign_keys() -> None:
    # SQLite's batch rebuild must not cascade-delete dependent event/notification rows.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite" and bind.scalar(sa.text("PRAGMA foreign_keys")):
        raise RuntimeError("Disable SQLite foreign_keys before the migration transaction")


def upgrade() -> None:
    _check_sqlite_foreign_keys()
    unique = next(c for c in sa.inspect(op.get_bind()).get_unique_constraints(TABLE)
                  if set(c["column_names"]) == {"job_id", "student_id"})
    with op.batch_alter_table(TABLE, naming_convention=NAMING) as batch:
        batch.drop_constraint(unique["name"] or LEGACY, type_="unique")
        batch.create_index(INDEX, ["job_id", "student_id"], unique=True,
                           postgresql_where=sa.text("status != 'withdrawn'"),
                           sqlite_where=sa.text("status != 'withdrawn'"))


def downgrade() -> None:
    # The old schema cannot represent reapplications. Refuse instead of removing history.
    duplicate = op.get_bind().scalar(sa.text(
        "SELECT 1 FROM applications GROUP BY job_id, student_id HAVING COUNT(*) > 1 LIMIT 1"
    ))
    if duplicate:
        raise RuntimeError("Cannot downgrade: reapplications exist; preserve consent history")
    _check_sqlite_foreign_keys()
    with op.batch_alter_table(TABLE, naming_convention=NAMING) as batch:
        batch.drop_index(INDEX)
        batch.create_unique_constraint(LEGACY, ["job_id", "student_id"])
