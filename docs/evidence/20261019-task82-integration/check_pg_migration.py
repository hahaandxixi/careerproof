"""Round-trip 0021 only in this run's disposable port-55437 database."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg

OUT = Path(__file__).resolve().parent
BACKEND = OUT.parents[2] / "backend"
URL = "postgresql://ci:ci@127.0.0.1:55437/cp_migration82"
ENV = {
    **os.environ,
    "DATABASE_URL": URL.replace("postgresql://", "postgresql+asyncpg://"),
    "APP_ENV": "test", "DEBUG": "false", "AI_EXTERNAL_ENABLED": "false",
    "AI_PROVIDER": "mock", "PYTHONIOENCODING": "utf-8",
}


def migration(label, *args):
    with (OUT / f"{label}.raw.out").open("xb") as handle:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=ENV,
            stdout=handle, stderr=subprocess.STDOUT, check=False,
        )
    assert result.returncode == 0, f"{label} failed; see preserved log"


async def setup():
    connection = await asyncpg.connect(URL)
    try:
        assert await connection.fetchval("SELECT current_database()") == "cp_migration82"
        await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await connection.close()


async def seed():
    connection = await asyncpg.connect(URL)
    try:
        user, job = uuid4(), uuid4()
        await connection.execute("""
            INSERT INTO users (id,email,password_hash,display_name,role,is_active,
                               version,created_at,updated_at)
            VALUES ($1,'migration@example.test','synthetic','Synthetic','ENTERPRISE',
                    true,1,now(),now())
        """, user)
        await connection.execute("""
            INSERT INTO jobs (id,created_by,title,company_name,description,status,
                              category,city,employment_type,version,created_at,updated_at)
            VALUES ($1,$2,'Pre-0021 fixture','Synthetic','Owned migration fixture',
                    'published','software','Test','internship',1,now(),now())
        """, job, user)
    finally:
        await connection.close()


async def inspect(expect_flags):
    connection = await asyncpg.connect(URL)
    try:
        row = await connection.fetchval(
            "SELECT (to_jsonb(j)-'is_demo'-'discovery_visible')::text FROM jobs j"
        )
        columns = [dict(record) for record in await connection.fetch("""
            SELECT column_name,is_nullable,column_default FROM information_schema.columns
            WHERE table_schema='public' AND table_name='jobs'
              AND column_name IN ('is_demo','discovery_visible') ORDER BY column_name
        """)]
        assert len(columns) == (2 if expect_flags else 0)
        if expect_flags:
            assert all(item["is_nullable"] == "NO" for item in columns)
            assert await connection.fetchval(
                "SELECT NOT is_demo AND discovery_visible FROM jobs"
            )
            index_count = await connection.fetchval("""
                SELECT count(*) FROM pg_indexes WHERE schemaname='public'
                  AND indexname IN ('ix_jobs_is_demo','ix_jobs_discovery_visible')
            """)
            assert index_count == 2
        return {"legacyRow": row, "flagColumns": columns,
                "revision": await connection.fetchval("SELECT version_num FROM alembic_version")}
    finally:
        await connection.close()


asyncio.run(setup())
migration("pg-00-to-0020", "upgrade", "0020_login_limits")
asyncio.run(seed())
before = asyncio.run(inspect(False))
migration("pg-01-upgrade-0021", "upgrade", "head")
up = asyncio.run(inspect(True))
migration("pg-02-model-check", "check")
migration("pg-03-downgrade-owned-only", "downgrade", "0020_login_limits")
down = asyncio.run(inspect(False))
migration("pg-04-reupgrade", "upgrade", "head")
again = asyncio.run(inspect(True))
assert before["legacyRow"] == up["legacyRow"] == down["legacyRow"] == again["legacyRow"]
with (OUT / "pg-migration-result.json").open("x", encoding="utf-8") as handle:
    json.dump({"dedicatedPort": 55437, "normalDatabaseTouched": False,
               "before": before, "upgraded": up, "downgraded": down,
               "reupgraded": again, "legacyFixturePreserved": True,
               "modelCheckPassed": True}, handle, indent=2)
print("Dedicated PG upgrade/check/downgrade/reupgrade passed; legacy fixture unchanged.")
