"""0016 real SQLite and isolated PostgreSQL upgrade/downgrade keeps legacy ledger intact.

The PostgreSQL fixture creates its own randomly named cp_test_* schema, verifies
current_schema() before migrating, and only ever drops that generated schema.
"""

import hashlib
import importlib.util
import os
import re
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic.migration import MigrationContext
from alembic.operations import Operations

LEDGER_COLUMNS = (
    "id", "created_at", "updated_at", "analysis_task_id", "model",
    "input_tokens", "output_tokens", "cache_hit_tokens", "unit_price_snapshot",
    "cost_rmb", "latency_ms", "run_token", "request_seq",
)
ATTEMPT_COLUMNS = (
    "id", "created_at", "updated_at", "analysis_task_id", "created_by", "run_token", "step",
    "physical_sequence", "provider", "model", "state", "sending_day",
    "estimated_input_tokens", "max_output_tokens", "usage_input_tokens", "usage_output_tokens",
    "usage_cache_hit_tokens", "latency_ms", "usage_raw", "response_digest", "send_intent_at",
    "receipt_at", "booked_at", "ended_at", "reason",
)
LEDGER_FK = "fk_ai_usage_logs_attempt_id"
LEDGER_INDEX = "uq_ai_usage_logs_attempt_id"


def migration(name):
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(rows):
    return hashlib.sha256(repr(sorted(rows)).encode("utf-8")).hexdigest()


def create_legacy_tables_sqlite(connection):
    connection.exec_driver_sql("CREATE TABLE users (id CHAR(32) PRIMARY KEY)")
    connection.exec_driver_sql(
        "CREATE TABLE analysis_tasks (id CHAR(32) PRIMARY KEY, created_by CHAR(32) "
        "REFERENCES users(id))"
    )
    connection.exec_driver_sql(
        "CREATE TABLE ai_usage_logs ("
        "id CHAR(32) PRIMARY KEY, created_at VARCHAR(64), updated_at VARCHAR(64), "
        "analysis_task_id CHAR(32) REFERENCES analysis_tasks(id), model VARCHAR(100), "
        "input_tokens INTEGER, output_tokens INTEGER, cache_hit_tokens INTEGER, "
        "unit_price_snapshot TEXT, cost_rmb NUMERIC(12,6), latency_ms INTEGER, "
        "run_token CHAR(32), request_seq INTEGER)"
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX uq_ai_usage_logs_run_token_request_seq ON ai_usage_logs "
        "(run_token, request_seq) WHERE run_token IS NOT NULL"
    )


def seed_legacy_rows_sqlite(connection):
    user_id, task_id, first_id, second_id = (uuid4().hex for _ in range(4))
    legacy_token = uuid4().hex
    connection.exec_driver_sql(f"INSERT INTO users VALUES ('{user_id}')")
    connection.exec_driver_sql(
        f"INSERT INTO analysis_tasks VALUES ('{task_id}', '{user_id}')"
    )
    connection.exec_driver_sql(
        f"INSERT INTO ai_usage_logs VALUES ('{first_id}', '2026-10-05T08:00:00Z', "
        f"'2026-10-05T08:00:00Z', '{task_id}', 'deepseek-chat', 120, 80, 0, "
        f"'{{\"price\":0.001}}', 0.0002, 1500, NULL, NULL)"
    )
    connection.exec_driver_sql(
        f"INSERT INTO ai_usage_logs VALUES ('{second_id}', '2026-10-05T09:00:00Z', "
        f"'2026-10-05T09:00:00Z', '{task_id}', 'deepseek-reasoner', 300, 500, 100, "
        f"'{{\"price\":0.002}}', 0.0014, 4200, '{legacy_token}', 1)"
    )
    return {"user": user_id, "task": task_id, "ledger_ids": [first_id, second_id]}


def ledger_rows(connection):
    query = "SELECT " + ", ".join(LEDGER_COLUMNS) + " FROM ai_usage_logs"
    return [tuple(row) for row in connection.exec_driver_sql(query).fetchall()]


def insert_attempt_sqlite(connection, ids, *, state, ended_at="NULL", reason="NULL"):
    attempt_id = uuid4().hex
    connection.exec_driver_sql(
        f"INSERT INTO ai_request_attempts (id, created_at, updated_at, analysis_task_id, "
        f"created_by, run_token, step, physical_sequence, provider, model, state, "
        f"estimated_input_tokens, max_output_tokens, usage_raw, ended_at, reason) VALUES ("
        f"'{attempt_id}', '2026-10-07T09:00:00Z', '2026-10-07T09:00:00Z', "
        f"'{ids['task']}', '{ids['user']}', '{uuid4().hex}', 'verify', 1, 'deepseek', "
        f"'deepseek-chat', '{state}', 100, 200, '{{}}', {ended_at}, {reason})"
    )
    return attempt_id


def test_sqlite_0016_upgrade_downgrade_preserves_legacy_ledger(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'attempt-migration.db'}")
    module = migration("0016_ai_request_attempts.py")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        create_legacy_tables_sqlite(connection)
        ids = seed_legacy_rows_sqlite(connection)
        original = ledger_rows(connection)
        original_digest = digest(original)
        assert len(original) == 2

        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()

        inspector = sa.inspect(connection)
        assert "ai_request_attempts" in inspector.get_table_names()
        columns = {column["name"] for column in inspector.get_columns("ai_request_attempts")}
        assert set(ATTEMPT_COLUMNS) <= columns
        ledger_columns = {
            column["name"]: column for column in inspector.get_columns("ai_usage_logs")
        }
        assert "attempt_id" in ledger_columns
        assert ledger_columns["attempt_id"]["nullable"] is True
        assert LEDGER_INDEX in {
            index["name"] for index in inspector.get_indexes("ai_usage_logs")
        }
        assert sorted(ledger_rows(connection)) == sorted(original)
        assert digest(ledger_rows(connection)) == original_digest

        booked_id = insert_attempt_sqlite(connection, ids, state="booked")
        ended_id = insert_attempt_sqlite(
            connection, ids, state="not_sent", ended_at="'2026-10-07T09:30:00Z'",
            reason="'explicitly not sent'",
        )
        unsettled_id = insert_attempt_sqlite(connection, ids, state="in_flight")
        connection.exec_driver_sql(
            f"INSERT INTO ai_usage_logs (id, created_at, updated_at, analysis_task_id, model, "
            f"input_tokens, output_tokens, cache_hit_tokens, unit_price_snapshot, cost_rmb, "
            f"latency_ms, run_token, request_seq, attempt_id) VALUES ("
            f"'{uuid4().hex}', '2026-10-07T10:00:00Z', '2026-10-07T10:00:00Z', '{ids['task']}', "
            f"'deepseek-chat', 100, 200, 0, '{{}}', 0.0, 1500, NULL, NULL, '{booked_id}')"
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(f"DELETE FROM ai_request_attempts WHERE id='{booked_id}'")
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(
                f"UPDATE ai_usage_logs SET attempt_id='{booked_id}' "
                f"WHERE id='{ids['ledger_ids'][0]}'"
            )

        with pytest.raises(RuntimeError), Operations.context(
            MigrationContext.configure(connection)
        ):
            module.downgrade()
        assert "ai_request_attempts" in sa.inspect(connection).get_table_names()
        assert "attempt_id" in {
            column["name"] for column in sa.inspect(connection).get_columns("ai_usage_logs")
        }

        connection.exec_driver_sql(f"DELETE FROM ai_usage_logs WHERE attempt_id='{booked_id}'")
        connection.exec_driver_sql(f"DELETE FROM ai_request_attempts WHERE id='{booked_id}'")
        for state in ("received_unbooked", "usage_unknown"):
            connection.exec_driver_sql(
                f"UPDATE ai_request_attempts SET state='{state}' WHERE id='{unsettled_id}'"
            )
            with pytest.raises(RuntimeError), Operations.context(
                MigrationContext.configure(connection)
            ):
                module.downgrade()
        connection.exec_driver_sql(
            f"UPDATE ai_request_attempts SET state='not_sent', ended_at=NULL "
            f"WHERE id='{unsettled_id}'"
        )
        with pytest.raises(RuntimeError), Operations.context(
            MigrationContext.configure(connection)
        ):
            module.downgrade()

        connection.exec_driver_sql(
            f"UPDATE ai_request_attempts SET state='not_sent', "
            f"ended_at='2026-10-07T09:30:00Z', reason='explicitly not sent' "
            f"WHERE id='{unsettled_id}'"
        )
        connection.exec_driver_sql(
            f"UPDATE ai_request_attempts SET state='booked', usage_input_tokens=10, "
            f"usage_output_tokens=20, usage_cache_hit_tokens=0, latency_ms=900, "
            f"response_digest='{uuid4().hex}' WHERE id='{ended_id}'"
        )
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()

        assert "ai_request_attempts" not in sa.inspect(connection).get_table_names()
        assert "attempt_id" not in {
            column["name"] for column in sa.inspect(connection).get_columns("ai_usage_logs")
        }
        assert sorted(ledger_rows(connection)) == sorted(original)
        assert digest(ledger_rows(connection)) == original_digest
    engine.dispose()


@pytest.fixture
async def attempt_pg(tmp_path):
    database_url = os.environ.get("CAREERPROOF_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Requires explicit PostgreSQL cp_test schema")
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("The integration database must use postgresql+asyncpg")
    schema_name = f"cp_test_{uuid4().hex}"
    assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema_name)
    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": f"{schema_name},public"}},
    )
    schema_created = False
    try:
        async with engine.begin() as connection:
            created = await connection.scalar(text(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name=:name"
            ), {"name": schema_name})
            if created:
                raise RuntimeError(f"Random cp_test schema {schema_name} already exists")
            await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        schema_created = True
        async with engine.begin() as connection:
            schema = await connection.scalar(text("SELECT current_schema()"))
            assert schema == schema_name, f"current_schema fell back to {schema!r}"
            assert schema != "public"
        yield engine, schema_name
    finally:
        if schema_created:
            assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema_name)
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await engine.dispose()


def run_migration(module, direction):
    def execute(sync):
        with Operations.context(MigrationContext.configure(sync)):
            getattr(module, direction)()

    return execute


async def test_postgres_0016_migration_inside_own_cp_test_schema(attempt_pg):
    engine, schema_name = attempt_pg
    module = migration("0016_ai_request_attempts.py")
    async with engine.connect() as connection:
        await connection.exec_driver_sql("CREATE TABLE users (id UUID PRIMARY KEY)")
        await connection.exec_driver_sql(
            "CREATE TABLE analysis_tasks (id UUID PRIMARY KEY, "
            "created_by UUID REFERENCES users(id))"
        )
        await connection.exec_driver_sql(
            "CREATE TABLE ai_usage_logs ("
            "id UUID PRIMARY KEY, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ, "
            "analysis_task_id UUID REFERENCES analysis_tasks(id), model VARCHAR(100), "
            "input_tokens INTEGER, output_tokens INTEGER, cache_hit_tokens INTEGER, "
            "unit_price_snapshot JSON, cost_rmb NUMERIC(12,6), latency_ms INTEGER, "
            "run_token UUID, request_seq INTEGER)"
        )
        await connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_ai_usage_logs_run_token_request_seq ON ai_usage_logs "
            "(run_token, request_seq) WHERE run_token IS NOT NULL"
        )
        user_id, task_id, first_id, second_id = (uuid4() for _ in range(4))
        legacy_token = uuid4()
        await connection.exec_driver_sql(f"INSERT INTO users VALUES ('{user_id}')")
        await connection.exec_driver_sql(
            f"INSERT INTO analysis_tasks VALUES ('{task_id}', '{user_id}')"
        )
        await connection.exec_driver_sql(
            f"INSERT INTO ai_usage_logs VALUES ('{first_id}', '2026-10-05T08:00:00Z', "
            f"'2026-10-05T08:00:00Z', '{task_id}', 'deepseek-chat', 120, 80, 0, "
            f"'{{}}'::json, 0.0002, 1500, NULL, NULL)"
        )
        await connection.exec_driver_sql(
            f"INSERT INTO ai_usage_logs VALUES ('{second_id}', '2026-10-05T09:00:00Z', "
            f"'2026-10-05T09:00:00Z', '{task_id}', 'deepseek-reasoner', 300, 500, 100, "
            f"'{{}}'::json, 0.0014, 4200, '{legacy_token}', 1)"
        )
        schema = await connection.scalar(text("SELECT current_schema()"))
        assert schema == schema_name and schema.startswith("cp_test_")
        query = text("SELECT " + ", ".join(LEDGER_COLUMNS) + " FROM ai_usage_logs")
        original = [tuple(row) for row in (await connection.execute(query)).fetchall()]
        assert len(original) == 2
        original_digest = digest(original)
        await connection.run_sync(run_migration(module, "upgrade"))

        constraint = await connection.scalar(text(
            "SELECT conname FROM pg_constraint WHERE conrelid='ai_usage_logs'::regclass "
            "AND contype='f' AND conname=:name"
        ), {"name": LEDGER_FK})
        assert constraint == LEDGER_FK
        assert await connection.scalar(text(
            "SELECT indexname FROM pg_indexes WHERE tablename='ai_usage_logs' "
            "AND indexname=:name"
        ), {"name": LEDGER_INDEX}) == LEDGER_INDEX
        assert await connection.scalar(text(
            "SELECT count(*) FROM pg_type WHERE typtype='e' AND typname LIKE '%attempt%'"
        )) == 0
        assert sorted(
            tuple(row) for row in (await connection.execute(query)).fetchall()
        ) == sorted(original)
        assert digest(
            [tuple(row) for row in (await connection.execute(query)).fetchall()]
        ) == original_digest

        booked_id = uuid4()
        await connection.exec_driver_sql(
            f"INSERT INTO ai_request_attempts (id, created_at, updated_at, analysis_task_id, "
            f"created_by, run_token, step, physical_sequence, provider, model, state, "
            f"estimated_input_tokens, max_output_tokens, usage_raw) VALUES ("
            f"'{booked_id}', '2026-10-07T09:00:00Z', '2026-10-07T09:00:00Z', '{task_id}', "
            f"'{user_id}', '{uuid4()}', 'verify', 1, 'deepseek', 'deepseek-chat', 'in_flight', "
            f"100, 200, '{{}}'::json)"
        )
        await connection.exec_driver_sql(
            f"UPDATE ai_usage_logs SET attempt_id='{booked_id}' WHERE id='{first_id}'"
        )
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.exec_driver_sql(
                    f"DELETE FROM ai_request_attempts WHERE id='{booked_id}'"
                )

        with pytest.raises(RuntimeError):
            await connection.run_sync(run_migration(module, "downgrade"))
        assert await connection.scalar(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema=:schema AND table_name='ai_request_attempts'"
        ), {"schema": schema_name}) == 1

        await connection.exec_driver_sql(
            f"UPDATE ai_usage_logs SET attempt_id=NULL WHERE id='{first_id}'"
        )
        await connection.exec_driver_sql(
            f"UPDATE ai_request_attempts SET state='booked', usage_input_tokens=100, "
            f"usage_output_tokens=200, usage_cache_hit_tokens=0, latency_ms=1500, "
            f"response_digest='{uuid4().hex}' WHERE id='{booked_id}'"
        )
        await connection.run_sync(run_migration(module, "downgrade"))

        assert await connection.scalar(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema=:schema AND table_name='ai_request_attempts'"
        ), {"schema": schema_name}) == 0
        assert await connection.scalar(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema=:schema AND table_name='ai_usage_logs' AND column_name='attempt_id'"
        ), {"schema": schema_name}) == 0
        assert sorted(
            tuple(row) for row in (await connection.execute(query)).fetchall()
        ) == sorted(original)
        assert digest(
            [tuple(row) for row in (await connection.execute(query)).fetchall()]
        ) == original_digest
