"""Real DDL: preserve snapshots/dependent events and refuse destructive downgrade."""

import pytest
import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.tests.test_ai_request_attempt_migration import migration

pytest_plugins = ["app.tests.test_ai_request_attempt_migration"]


def exercise(connection):
    # Minimal populated legacy schema, including a cascading dependent table.
    connection.exec_driver_sql("CREATE TABLE applications (id VARCHAR(36) PRIMARY KEY, "
        "job_id VARCHAR(36) NOT NULL, student_id VARCHAR(36) NOT NULL, "
        "status VARCHAR(30) NOT NULL, report_snapshot TEXT NOT NULL, "
        "UNIQUE (job_id, student_id))")
    connection.exec_driver_sql("CREATE TABLE application_events (id VARCHAR(36) PRIMARY KEY, "
        "application_id VARCHAR(36) REFERENCES applications(id) ON DELETE CASCADE, "
        "detail TEXT)")
    connection.exec_driver_sql("INSERT INTO applications VALUES "
        "('old','job','student','withdrawn','{\"summary\":\"frozen\"}')")
    connection.exec_driver_sql("INSERT INTO application_events VALUES "
        "('event','old','withdrawn')")
    original = connection.exec_driver_sql("SELECT * FROM applications").all()
    events = connection.exec_driver_sql("SELECT * FROM application_events").all()
    module = migration("0018_application_reconsent.py")
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()
    assert connection.exec_driver_sql("SELECT * FROM applications").all() == original
    assert connection.exec_driver_sql("SELECT * FROM application_events").all() == events
    # Safe round trip with only legacy data.
    with Operations.context(MigrationContext.configure(connection)):
        module.downgrade()
        module.upgrade()
    connection.exec_driver_sql("INSERT INTO applications VALUES "
        "('new','job','student','submitted','{\"summary\":\"new\"}')")
    with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
        connection.exec_driver_sql("INSERT INTO applications VALUES "
            "('duplicate','job','student','submitted','{}')")
    # No history deletion or index removal when old schema cannot represent the data.
    with pytest.raises(RuntimeError, match="preserve consent history"), Operations.context(
        MigrationContext.configure(connection)
    ):
        module.downgrade()
    assert len(connection.exec_driver_sql("SELECT * FROM applications").all()) == 2
    assert connection.exec_driver_sql("SELECT * FROM application_events").all() == events
    assert "uq_applications_active_job_student" in {
        i["name"] for i in sa.inspect(connection).get_indexes("applications")
    }


def test_sqlite_reconsent_migration_preserves_history(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    try:
        with engine.begin() as connection:
            exercise(connection)
    finally:
        engine.dispose()


async def test_postgres_reconsent_migration_preserves_history(attempt_pg):
    engine, schema = attempt_pg
    async with engine.begin() as connection:
        assert await connection.scalar(sa.text("SELECT current_schema()")) == schema
        await connection.run_sync(exercise)


def test_sqlite_migration_rejects_cascading_batch_rebuild(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'guard.db'}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            with pytest.raises(RuntimeError, match="foreign_keys"), Operations.context(
                MigrationContext.configure(connection)
            ):
                migration("0018_application_reconsent.py").upgrade()
    finally:
        engine.dispose()
