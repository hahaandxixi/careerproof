"""Real Alembic env.py 0001..0016 and 0016 roundtrip, only an owned schema."""

import asyncio
import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

helper_path = Path(__file__).parents[1] / "20261006-PRODUCT-01-migration-chain/verify_chain.py"
spec = importlib.util.spec_from_file_location("ops_guarded_migration", helper_path)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
REVISION = "0016_ai_request_attempts"
LEDGER_ID = uuid4()


async def ledger_snapshot():
    engine = guard.engine()
    try:
        async with engine.connect() as connection:
            await guard.assert_schema(connection)
            namespace = await connection.scalar(text(
                "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.oid=to_regclass('ai_usage_logs')"
            ))
            assert namespace == guard.SCHEMA
            row = await connection.scalar(text(
                "SELECT row_to_json(t) FROM (SELECT id,created_at,updated_at,analysis_task_id,"
                "model,input_tokens,output_tokens,cache_hit_tokens,unit_price_snapshot,"
                "cost_rmb,latency_ms,run_token,request_seq FROM ai_usage_logs WHERE id=:id) t"
            ), {"id": LEDGER_ID})
            assert row is not None
            return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()
    finally:
        await engine.dispose()


async def seed_ledger(task_id):
    engine = guard.engine()
    try:
        async with engine.begin() as connection:
            await guard.assert_schema(connection)
            for table in ("users", "analysis_tasks", "ai_usage_logs"):
                assert await connection.scalar(text(
                    "SELECT n.nspname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=to_regclass(:table)"
                ), {"table": table}) == guard.SCHEMA
            await connection.execute(text(
                "INSERT INTO ai_usage_logs (id,created_at,updated_at,analysis_task_id,model,"
                "input_tokens,output_tokens,cache_hit_tokens,unit_price_snapshot,cost_rmb,"
                "latency_ms,run_token,request_seq) VALUES (:id,:now,:now,:task,'synthetic-legacy',"
                "123,45,17,'{}',0.004,200,:run,1)"
            ), {"id": LEDGER_ID, "now": datetime.now(UTC), "task": task_id, "run": uuid4()})
    finally:
        await engine.dispose()


def main():
    assert Path.cwd().resolve() == guard.BACKEND.resolve()
    created = False
    try:
        asyncio.run(guard.preflight())
        created = True
        guard.migration("upgrade", guard.REV15)
        asyncio.run(guard.stage(guard.REV15))
        ids = asyncio.run(guard.seed())
        asyncio.run(seed_ledger(ids["task"]))
        before = asyncio.run(ledger_snapshot())
        business = asyncio.run(guard.rows_snapshot(ids))
        for direction, revision in (("upgrade", REVISION), ("downgrade", guard.REV15),
                                    ("upgrade", REVISION)):
            guard.migration(direction, revision)
            assert asyncio.run(guard.scalar("SELECT version_num FROM alembic_version")) == revision
            assert asyncio.run(ledger_snapshot()) == before
            assert asyncio.run(guard.rows_snapshot(ids)) == business
            print(f"STAGE {revision}: legacyLedgerSHA256={before}; oldBusinessRowsUnchanged=1")
        print("RESULT PASS real env.py base..0016 and 0016..0015..0016, legacy facts unchanged")
    finally:
        if created:
            asyncio.run(guard.cleanup())


if __name__ == "__main__":
    main()
