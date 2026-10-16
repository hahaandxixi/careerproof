"""0020 creates only ephemeral admission state, preserving existing identity rows."""

import pytest
import sqlalchemy as sa

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.models.login_limit import LoginLimit
from app.tests.test_ai_request_attempt_migration import attempt_pg as attempt_pg
from app.tests.test_ai_request_attempt_migration import migration


def exercise(connection):
    connection.exec_driver_sql("CREATE TABLE existing_identity (id INTEGER PRIMARY KEY, name TEXT)")
    connection.exec_driver_sql("INSERT INTO existing_identity VALUES (1, 'synthetic unchanged')")
    module = migration("0020_login_limits.py")
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()
    table = LoginLimit.__table__
    connection.execute(table.insert().values(
        key_hash="a" * 64, scope="source", attempts=1, expires_at=1_800_000_000,
    ))
    for values in [{"attempts": 0}, {"scope": "bypass"}]:
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.execute(table.update().values(**values))
    expected = sa.MetaData()
    table.to_metadata(expected)
    context = MigrationContext.configure(connection, opts={
        "include_object": lambda obj, name, type_, reflected, compare_to:
            not (type_ == "table" and name != "login_limits"),
        "compare_type": True,
    })
    assert compare_metadata(context, expected) == []
    with Operations.context(MigrationContext.configure(connection)):
        module.downgrade()
    assert "login_limits" not in sa.inspect(connection).get_table_names()
    assert connection.exec_driver_sql("SELECT * FROM existing_identity").all() == [
        (1, "synthetic unchanged"),
    ]
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()
    assert connection.scalar(sa.select(sa.func.count()).select_from(table)) == 0


def test_sqlite_login_limit_migration_roundtrip(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'login-limit-migration.db'}")
    try:
        with engine.begin() as connection:
            exercise(connection)
    finally:
        engine.dispose()


async def test_pg_login_limit_migration_roundtrip(attempt_pg):  # noqa: F811
    engine, _ = attempt_pg
    async with engine.begin() as connection:
        await connection.run_sync(exercise)
