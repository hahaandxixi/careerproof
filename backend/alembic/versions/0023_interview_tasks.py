"""Link practice generation to the shared task lifecycle."""

import sqlalchemy as sa

from alembic import op

revision = "0023_interview_tasks"
down_revision = "0022_interview_practice"
branch_labels = None
depends_on = None


_LINKS = (("interview_sessions", "question_task_id"), ("interview_answers", "feedback_task_id"))


def upgrade():
    for table, column in _LINKS:
        if op.get_bind().dialect.name == "sqlite":
            # Add a nullable inline FK without rebuilding the historical tables.
            op.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} CHAR(32) "
                "REFERENCES analysis_tasks(id) ON DELETE SET NULL"
            )
        else:
            op.add_column(table, sa.Column(column, sa.Uuid(), nullable=True))
            op.create_foreign_key(
                f"fk_{table}_{column}",
                table,
                "analysis_tasks",
                [column],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade():
    for table, column in reversed(_LINKS):
        if op.get_bind().dialect.name != "sqlite":
            op.drop_constraint(f"fk_{table}_{column}", table, type_="foreignkey")
        op.drop_column(table, column)
