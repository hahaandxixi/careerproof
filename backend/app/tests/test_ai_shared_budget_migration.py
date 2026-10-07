"""Budget DDL contracts; admission and wire behavior require separate service tests."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.models.ai_budget import (
    AiBudgetAdjustment,
    AiBudgetCutover,
    AiBudgetReservation,
    AiDailyBudget,
)
from app.tests.test_ai_request_attempt_migration import (
    attempt_pg as attempt_pg,
)
from app.tests.test_ai_request_attempt_migration import (
    create_legacy_tables_sqlite,
    digest,
    insert_attempt_sqlite,
    ledger_rows,
    migration,
    seed_legacy_rows_sqlite,
)


@pytest.fixture
def budget_schema(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'budget-ddl.db'}")
    module = migration("0017_ai_shared_budget.py")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        create_legacy_tables_sqlite(connection)
        ids = seed_legacy_rows_sqlite(connection)
        with Operations.context(MigrationContext.configure(connection)):
            migration("0016_ai_request_attempts.py").upgrade()
        attempt_id = insert_attempt_sqlite(connection, ids, state="usage_unknown")
        before = digest(ledger_rows(connection))
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        yield connection, module, ids, attempt_id, before
    engine.dispose()


def reservation(ids, attempt_id, **extra):
    now = datetime.now(UTC)
    return dict(
        id=uuid4(),
        attempt_id=UUID(attempt_id),
        analysis_task_id=UUID(ids["task"]),
        created_by=UUID(ids["user"]),
        run_token=uuid4(),
        reservation_day=date(2026, 10, 7),
        input_bound=100,
        output_bound=200,
        state="held",
        source="pre_budget_attempt",
        created_at=now,
        updated_at=now,
        **extra,
    )


def test_budget_empty_roundtrip_preserves_legacy_and_attempt(budget_schema):
    connection, module, _ids, attempt_id, before = budget_schema
    original = list(connection.exec_driver_sql("SELECT * FROM ai_request_attempts"))
    assert digest(ledger_rows(connection)) == before
    with Operations.context(MigrationContext.configure(connection)):
        module.downgrade()
        module.upgrade()
    assert digest(ledger_rows(connection)) == before
    assert list(connection.exec_driver_sql("SELECT * FROM ai_request_attempts")) == original
    assert original[0].id == attempt_id
    for cls in (AiDailyBudget, AiBudgetReservation, AiBudgetAdjustment, AiBudgetCutover):
        reflected = sa.inspect(connection).get_columns(cls.__tablename__)
        assert {c["name"] for c in reflected} == set(cls.__table__.columns.keys())
        checks = {
            c["name"] for c in sa.inspect(connection).get_check_constraints(cls.__tablename__)
        }
        assert checks == {
            c.name for c in cls.__table__.constraints if isinstance(c, sa.CheckConstraint)
        }


@pytest.mark.parametrize(
    "changes",
    [
        {"input_bound": -1},
        {"state": "settled"},
        {"actual_input_tokens": 0, "actual_output_tokens": 0},
        {"state": "adjusted"},
        {"state": "invented"},
    ],
)
def test_budget_rejects_negative_or_fabricated_receipt(budget_schema, changes):
    connection, _module, ids, attempt_id, _before = budget_schema
    row = reservation(ids, attempt_id)
    row.update(changes)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(sa.insert(AiBudgetReservation), row)


def test_budget_one_reservation_and_real_zero_receipt(budget_schema):
    connection, module, ids, attempt_id, _before = budget_schema
    row = reservation(ids, attempt_id)
    row.update(
        state="settled", actual_input_tokens=0, actual_output_tokens=0, settled_at=datetime.now(UTC)
    )
    connection.execute(sa.insert(AiBudgetReservation), row)
    duplicate = {**row, "id": uuid4()}
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(sa.insert(AiBudgetReservation), duplicate)
    with (
        pytest.raises(RuntimeError, match="persistent budget data remains"),
        Operations.context(
            MigrationContext.configure(connection),
        ),
    ):
        module.downgrade()
    assert connection.scalar(sa.select(sa.func.count()).select_from(AiBudgetReservation)) == 1


def test_cutover_is_disabled_without_activation_evidence(budget_schema):
    connection, module, ids, _attempt_id, _before = budget_schema
    now = datetime.now(UTC)
    connection.execute(
        sa.insert(AiBudgetCutover),
        dict(
            id="shared_daily_v1",
            created_at=now,
            updated_at=now,
        ),
    )
    assert connection.scalar(sa.select(AiBudgetCutover.enabled)) is False
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(sa.update(AiBudgetCutover).values(enabled=True))
    connection.execute(
        sa.update(AiBudgetCutover).values(
            enabled=True,
            inventory_digest="a" * 64,
            activated_at=now,
            activated_by=UUID(ids["user"]),
            reason="synthetic audited inventory",
        )
    )
    with pytest.raises(RuntimeError), Operations.context(MigrationContext.configure(connection)):
        module.downgrade()
    # Activation evidence is persistent; the production service must independently
    # verify the inventory and administrator. A DDL row is not authorization.
    assert connection.scalar(sa.select(AiBudgetCutover.enabled)) is True


def test_owner_day_serialization_identity_unique(budget_schema):
    connection, _module, ids, _attempt_id, _before = budget_schema
    row = dict(
        id=uuid4(),
        created_by=UUID(ids["user"]),
        budget_day=date(2026, 10, 7),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    connection.execute(sa.insert(AiDailyBudget), row)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(sa.insert(AiDailyBudget), {**row, "id": uuid4()})


def test_adjustment_reason_and_operation_identity(budget_schema):
    connection, module, ids, attempt_id, _before = budget_schema
    hold = reservation(ids, attempt_id)
    connection.execute(sa.insert(AiBudgetReservation), hold)
    now = datetime.now(UTC)
    audit = dict(
        id=uuid4(),
        reservation_id=hold["id"],
        operation_id="synthetic-once",
        created_by=UUID(ids["user"]),
        actor_id=UUID(ids["user"]),
        reason="reviewed synthetic hold",
        before_input_tokens=100,
        before_output_tokens=200,
        after_input_tokens=0,
        after_output_tokens=0,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(sa.insert(AiBudgetAdjustment), {**audit, "reason": " "})
    connection.execute(sa.insert(AiBudgetAdjustment), audit)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(sa.insert(AiBudgetAdjustment), {**audit, "id": uuid4()})
    with pytest.raises(RuntimeError), Operations.context(MigrationContext.configure(connection)):
        module.downgrade()
    assert connection.scalar(sa.select(AiBudgetReservation.state)) == "held"


async def test_postgres_budget_roundtrip_and_unknown_downgrade_guard(
    attempt_pg,  # noqa: F811 - imported pytest fixture
):
    engine, schema_name = attempt_pg
    module = migration("0017_ai_shared_budget.py")

    def exercise(connection):
        assert connection.scalar(sa.text("SELECT current_schema()")) == schema_name
        connection.exec_driver_sql("CREATE TABLE users (id UUID PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE analysis_tasks (id UUID PRIMARY KEY, "
            "created_by UUID REFERENCES users(id))",
        )
        connection.exec_driver_sql(
            "CREATE TABLE ai_usage_logs (id UUID PRIMARY KEY, created_at TIMESTAMPTZ, "
            "updated_at TIMESTAMPTZ, analysis_task_id UUID REFERENCES analysis_tasks(id), "
            "model VARCHAR(100), input_tokens INTEGER, output_tokens INTEGER, "
            "cache_hit_tokens INTEGER, unit_price_snapshot JSON, cost_rmb NUMERIC(12,6), "
            "latency_ms INTEGER, run_token UUID, request_seq INTEGER)",
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration("0016_ai_request_attempts.py").upgrade()
            module.upgrade()
        for name in (
            "users",
            "analysis_tasks",
            "ai_usage_logs",
            "ai_request_attempts",
            *module.TABLES,
        ):
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT n.nspname FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE c.oid=to_regclass(:name)",
                    ),
                    {"name": name},
                )
                == schema_name
            )
        owner, task, attempt, token = (uuid4() for _ in range(4))
        connection.execute(sa.text("INSERT INTO users VALUES (:id)"), {"id": owner})
        connection.execute(
            sa.text("INSERT INTO analysis_tasks VALUES (:id,:owner)"),
            {
                "id": task,
                "owner": owner,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO ai_usage_logs "
                "(id, analysis_task_id, model, input_tokens, output_tokens) "
                "VALUES (:id,:task,'synthetic-legacy',11,13)",
            ),
            {"id": uuid4(), "task": task},
        )
        original = ledger_rows(connection)
        from app.models.ai_request_attempt import AiRequestAttempt

        connection.execute(
            sa.insert(AiRequestAttempt),
            dict(
                id=attempt,
                analysis_task_id=task,
                created_by=owner,
                run_token=token,
                step="analysis",
                physical_sequence=1,
                provider="synthetic",
                model="synthetic",
                state="usage_unknown",
                estimated_input_tokens=100,
                max_output_tokens=200,
            ),
        )
        before = list(connection.exec_driver_sql("SELECT * FROM ai_request_attempts"))
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
            module.upgrade()
        assert ledger_rows(connection) == original
        assert list(connection.exec_driver_sql("SELECT * FROM ai_request_attempts")) == before
        hold = reservation({"task": task.hex, "user": owner.hex}, attempt.hex)
        hold["run_token"] = token
        connection.execute(sa.insert(AiBudgetReservation), hold)
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(sa.insert(AiBudgetReservation), {**hold, "id": uuid4()})
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                sa.update(AiBudgetReservation).values(
                    actual_input_tokens=0,
                    actual_output_tokens=0,
                )
            )
        with (
            pytest.raises(RuntimeError),
            Operations.context(MigrationContext.configure(connection)),
        ):
            module.downgrade()
        assert connection.scalar(sa.select(AiBudgetReservation.state)) == "held"
        assert ledger_rows(connection) == original
        assert list(connection.exec_driver_sql("SELECT * FROM ai_request_attempts")) == before

    async with engine.begin() as connection:
        await connection.run_sync(exercise)
