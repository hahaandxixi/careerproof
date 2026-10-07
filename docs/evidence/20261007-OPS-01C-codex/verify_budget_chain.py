"""Real base..0017 and guarded rollback in a disposable, validated cp_test schema."""

import asyncio
import importlib.util
from pathlib import Path

from sqlalchemy import text

source = Path(__file__).parents[1] / "20261007-OPS-01B-codex/verify_full_chain.py"
spec = importlib.util.spec_from_file_location("previous_attempt_chain_proof", source)
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)
guard = proof.guard
REV16 = "0016_ai_request_attempts"
REV17 = "0017_ai_shared_budget"
TABLES = (
    "ai_daily_budgets",
    "ai_budget_reservations",
    "ai_budget_adjustments",
    "ai_budget_cutover",
)


async def budget_namespace():
    engine = guard.engine()
    try:
        async with engine.connect() as connection:
            await guard.assert_schema(connection)
            for name in TABLES:
                assert (
                    await connection.scalar(
                        text(
                            "SELECT n.nspname FROM pg_class c "
                            "JOIN pg_namespace n ON n.oid=c.relnamespace "
                            "WHERE c.oid=to_regclass(:name)",
                        ),
                        {"name": name},
                    )
                    == guard.SCHEMA
                )
                assert await connection.scalar(text(f"SELECT COUNT(*) FROM {name}")) == 0
    finally:
        await engine.dispose()


async def seed_capacity(owner):
    engine = guard.engine()
    try:
        async with engine.begin() as connection:
            await guard.assert_schema(connection)
            await connection.execute(
                text(
                    "INSERT INTO ai_daily_budgets "
                    "(id,created_by,budget_day,policy_version,created_at,updated_at) "
                    "VALUES (:id,:owner,'2026-10-08',1,NOW(),NOW())",
                ),
                {"id": proof.uuid4(), "owner": owner},
            )
    finally:
        await engine.dispose()


def main():
    assert Path.cwd().resolve() == guard.BACKEND.resolve()
    created = False
    try:
        asyncio.run(guard.preflight())
        created = True
        guard.migration("upgrade", REV16)
        ids = asyncio.run(guard.seed())
        asyncio.run(proof.seed_ledger(ids["task"]))
        before = asyncio.run(proof.ledger_snapshot())
        business = asyncio.run(guard.rows_snapshot(ids))
        for direction, revision in (("upgrade", REV17), ("downgrade", REV16), ("upgrade", REV17)):
            guard.migration(direction, revision)
            assert asyncio.run(guard.scalar("SELECT version_num FROM alembic_version")) == revision
            assert asyncio.run(proof.ledger_snapshot()) == before
            assert asyncio.run(guard.rows_snapshot(ids)) == business
            if revision == REV17:
                asyncio.run(budget_namespace())
            print(f"STAGE {revision}: legacyLedgerSHA256={before}; oldBusinessRowsUnchanged=1")
        asyncio.run(seed_capacity(ids["user"]))
        try:
            guard.migration("downgrade", REV16)
        except RuntimeError as exc:
            assert "persistent budget data remains" in str(exc)
            print("DATA DOWNGRADE REJECTED: PASS; persistent capacity retained")
        else:
            raise AssertionError("Budget data was silently destroyed")
        assert asyncio.run(guard.scalar("SELECT version_num FROM alembic_version")) == REV17
        assert asyncio.run(guard.scalar("SELECT COUNT(*) FROM ai_daily_budgets")) == 1
        assert asyncio.run(proof.ledger_snapshot()) == before
        assert asyncio.run(guard.rows_snapshot(ids)) == business
        print("RESULT PASS real env.py base..0017, empty 17..16..17, populated refusal")
    finally:
        if created:
            asyncio.run(guard.cleanup())


if __name__ == "__main__":
    main()
