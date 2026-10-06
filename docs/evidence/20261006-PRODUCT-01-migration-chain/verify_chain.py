"""Isolated, disposable PostgreSQL Alembic env.py chain check.

Run from backend: .venv/Scripts/python.exe ../docs/evidence/20261006-PRODUCT-01-migration-chain/verify_chain.py
Only the generated cp_test_<uuid> schema is created and dropped.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


BACKEND = Path(__file__).resolve().parents[3] / "backend"
URL = "postgresql+asyncpg://careerproof:careerproof@127.0.0.1:5432/careerproof"
SCHEMA = f"cp_test_{uuid4().hex}"
assert re.fullmatch(r"cp_test_[0-9a-f]{32}", SCHEMA)
SEARCH_PATH = f"{SCHEMA},public"
REV14 = "0014_growth_target_job"
REV15 = "0015_growth_answer_drafts"


def engine():
    return create_async_engine(
        URL,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": SEARCH_PATH}},
    )


async def assert_schema(connection):
    actual = await connection.scalar(text("SELECT current_schema()"))
    assert actual == SCHEMA, f"Unsafe schema: {actual!r} != {SCHEMA!r}"


class GuardedEngine:
    def __init__(self):
        self._engine = engine()

    @asynccontextmanager
    async def connect(self):
        async with self._engine.connect() as connection:
            await assert_schema(connection)
            # End the preflight SELECT transaction before Alembic begins its own.
            await connection.rollback()
            yield connection

    async def dispose(self):
        await self._engine.dispose()


def migration(direction: str, revision: str):
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    calls = []

    def guarded_factory(*_args, **_kwargs):
        calls.append(True)
        return GuardedEngine()

    # env.py imports this function and uses the returned engine itself.
    # Its settings-derived URL is never opened in this process.
    with patch("sqlalchemy.ext.asyncio.async_engine_from_config", guarded_factory):
        getattr(command, direction)(cfg, revision)
    assert calls == [True], f"Unexpected env.py engine calls: {len(calls)}"
    print(f"MIGRATION {direction} {revision}: PASS; guarded env.py engine calls=1", flush=True)


async def preflight():
    e = engine()
    try:
        async with e.begin() as c:
            db = await c.scalar(text("SELECT current_database()"))
            assert db == "careerproof", f"Unexpected database: {db!r}"
            exists = await c.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :name)"),
                {"name": SCHEMA},
            )
            assert not exists, "Generated schema unexpectedly exists"
            ext_schema = await c.scalar(
                text("SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'")
            )
            assert ext_schema == "public", f"vector extension preflight failed: {ext_schema!r}"
            await c.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
            await assert_schema(c)
            own_objects = await c.scalar(
                text("SELECT COUNT(*) FROM pg_class WHERE relnamespace = (SELECT oid FROM pg_namespace WHERE nspname=:name)"),
                {"name": SCHEMA},
            )
            assert own_objects == 0
            # env.py does not configure version_table_schema. Without this local
            # shadow table, Alembic resolves public.alembic_version and could
            # migrate public. The schema was empty before this bookkeeping DDL.
            await c.execute(text(f'CREATE TABLE "{SCHEMA}".alembic_version (version_num varchar(32) NOT NULL PRIMARY KEY)'))
            local_version_count = await c.scalar(text(f'SELECT COUNT(*) FROM "{SCHEMA}".alembic_version'))
            assert local_version_count == 0
        print(f"PREFLIGHT PASS database=careerproof schema={SCHEMA} empty=1 vector=public", flush=True)
        print("LOCAL ALEMBIC VERSION TABLE PASS empty=1", flush=True)
    finally:
        await e.dispose()


async def scalar(sql: str, params: dict | None = None):
    e = engine()
    try:
        async with e.connect() as c:
            await assert_schema(c)
            return await c.scalar(text(sql), params or {})
    finally:
        await e.dispose()


async def stage(revision: str):
    actual = await scalar("SELECT version_num FROM alembic_version")
    assert actual == revision, f"Expected {revision}, found {actual}"
    table = await scalar(
        "SELECT to_regclass(:name)", {"name": f"{SCHEMA}.growth_answer_drafts"}
    )
    assert (table is not None) == (revision == REV15)
    print(f"STAGE {revision}: PASS; draft_table={table is not None}", flush=True)


def digest(rows):
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


async def rows_snapshot(ids):
    e = engine()
    try:
        async with e.connect() as c:
            await assert_schema(c)
            out = {}
            for table, pk in (("evidence_growth_tasks", ids["growth"]), ("match_reports", ids["report"]), ("applications", ids["application"])):
                row = (await c.execute(text(f"SELECT row_to_json(t)::text FROM {table} t WHERE id=:id"), {"id": pk})).scalar_one()
                out[table] = json.loads(row)
            return digest(out)
    finally:
        await e.dispose()


async def seed():
    ids = {k: uuid4() for k in ("user", "profile", "job", "task", "report", "application", "growth")}
    now = datetime.now(timezone.utc)
    common = {"created_at": now, "updated_at": now}
    e = engine()
    try:
        async with e.begin() as c:
            await assert_schema(c)
            await c.execute(text("INSERT INTO users (id,email,password_hash,display_name,role,is_active,version,created_at,updated_at) VALUES (:id,:email,'synthetic','Synthetic Student','STUDENT',true,1,:created_at,:updated_at)"), {**common, "id": ids["user"], "email": f"synthetic-{ids['user'].hex}@example.invalid"})
            await c.execute(text("INSERT INTO student_profiles (id,user_id,version,created_at,updated_at) VALUES (:id,:user_id,1,:created_at,:updated_at)"), {**common, "id": ids["profile"], "user_id": ids["user"]})
            await c.execute(text("INSERT INTO jobs (id,created_by,title,company_name,description,status,version,category,city,employment_type,created_at,updated_at) VALUES (:id,:user_id,'Synthetic Job','Example.invalid','Synthetic only','published',1,'software','Test','campus',:created_at,:updated_at)"), {**common, "id": ids["job"], "user_id": ids["user"]})
            await c.execute(text("INSERT INTO analysis_tasks (id,created_by,task_type,status,progress,total_cost_rmb,version,attempt,input_snapshot,created_at,updated_at) VALUES (:id,:user_id,'matching','COMPLETED',100,0,1,0,CAST(:snapshot AS json),:created_at,:updated_at)"), {**common, "id": ids["task"], "user_id": ids["user"], "snapshot": json.dumps({"synthetic": True})})
            await c.execute(text("INSERT INTO match_reports (id,analysis_task_id,job_id,candidate_ref,overall_score,summary,gaps,claimed_only,candidate_name,job_snapshot,materials_snapshot,analysis_metadata,version,created_at,updated_at) VALUES (:id,:task_id,:job_id,'synthetic-ref',72.5,'Synthetic report',CAST(:gaps AS json),CAST(:claimed AS json),'Synthetic Student',CAST(:job_snapshot AS json),CAST(:materials AS json),CAST(:metadata AS json),1,:created_at,:updated_at)"), {**common, "id": ids["report"], "task_id": ids["task"], "job_id": ids["job"], "gaps": json.dumps(["synthetic-gap"]), "claimed": "[]", "job_snapshot": json.dumps({"title": "Synthetic Job"}), "materials": "[]", "metadata": "{}"})
            await c.execute(text("INSERT INTO applications (id,job_id,student_id,status,version,report_id,report_snapshot,reply_references,created_at,updated_at) VALUES (:id,:job_id,:student_id,'submitted',1,:report_id,CAST(:snapshot AS json),CAST(:refs AS json),:created_at,:updated_at)"), {**common, "id": ids["application"], "job_id": ids["job"], "student_id": ids["profile"], "report_id": ids["report"], "snapshot": json.dumps({"synthetic": "application"}), "refs": "[]"})
            await c.execute(text("INSERT INTO evidence_growth_tasks (id,created_by,base_report_id,requirement_id,base_snapshot,plan,materials,status,target_job_id,created_at,updated_at) VALUES (:id,:user_id,:report_id,:requirement_id,CAST(:base AS json),CAST(:plan AS json),CAST(:materials AS json),'pending',:job_id,:created_at,:updated_at)"), {**common, "id": ids["growth"], "user_id": ids["user"], "report_id": ids["report"], "requirement_id": uuid4(), "job_id": ids["job"], "base": json.dumps({"synthetic": "frozen"}), "plan": "{}", "materials": "[]"})
        print("SEED PASS synthetic growth/report/application rows committed", flush=True)
        return ids
    finally:
        await e.dispose()


async def check_draft(ids):
    e = engine()
    now = datetime.now(timezone.utc)
    try:
        async with e.begin() as c:
            await assert_schema(c)
            await c.execute(text("INSERT INTO growth_answer_drafts (id,growth_task_id,text,\"references\",revision,created_at,updated_at) VALUES (:id,:growth_id,'Synthetic private draft',CAST(:refs AS json),1,:now,:now)"), {"id": uuid4(), "growth_id": ids["growth"], "refs": json.dumps([{"source": "synthetic"}]), "now": now})
            count = await c.scalar(text("SELECT COUNT(*) FROM growth_answer_drafts WHERE growth_task_id=:id"), {"id": ids["growth"]})
            assert count == 1
            try:
                async with c.begin_nested():
                    await c.execute(text("INSERT INTO growth_answer_drafts (id,growth_task_id,text,\"references\",revision,created_at,updated_at) VALUES (:id,:growth_id,'duplicate','[]',1,:now,:now)"), {"id": uuid4(), "growth_id": ids["growth"], "now": now})
                raise AssertionError("Unique growth_task_id constraint did not reject duplicate")
            except Exception as exc:
                if isinstance(exc, AssertionError):
                    raise
                assert "unique" in str(exc).lower()
            try:
                async with c.begin_nested():
                    await c.execute(text("INSERT INTO growth_answer_drafts (id,growth_task_id,text,\"references\",revision,created_at,updated_at) VALUES (:id,:growth_id,'orphan','[]',1,:now,:now)"), {"id": uuid4(), "growth_id": uuid4(), "now": now})
                raise AssertionError("FK did not reject orphan")
            except Exception as exc:
                if isinstance(exc, AssertionError):
                    raise
                assert "foreign key" in str(exc).lower()
        print("DRAFT PASS insert/read, unique, FK", flush=True)
    finally:
        await e.dispose()


async def cleanup():
    assert re.fullmatch(r"cp_test_[0-9a-f]{32}", SCHEMA)
    e = engine()
    try:
        async with e.begin() as c:
            await assert_schema(c)
            await c.execute(text(f'DROP SCHEMA "{SCHEMA}" CASCADE'))
            exists = await c.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=:name)"), {"name": SCHEMA})
            assert not exists
        print(f"CLEANUP PASS schema={SCHEMA}", flush=True)
    finally:
        await e.dispose()


def main():
    assert Path.cwd().resolve() == BACKEND.resolve(), "Run from backend directory"
    created = False
    try:
        asyncio.run(preflight())
        created = True
        migration("upgrade", REV14)
        asyncio.run(stage(REV14))
        ids = asyncio.run(seed())
        before = asyncio.run(rows_snapshot(ids))
        print(f"LEGACY SHA256 before={before}", flush=True)
        migration("upgrade", REV15)
        asyncio.run(stage(REV15))
        asyncio.run(check_draft(ids))
        at15 = asyncio.run(rows_snapshot(ids))
        assert at15 == before
        print(f"LEGACY SHA256 at0015={at15} unchanged=1", flush=True)
        migration("downgrade", REV14)
        asyncio.run(stage(REV14))
        at14 = asyncio.run(rows_snapshot(ids))
        assert at14 == before
        print(f"LEGACY SHA256 after_downgrade={at14} unchanged=1", flush=True)
        migration("upgrade", REV15)
        asyncio.run(stage(REV15))
        asyncio.run(check_draft(ids))
        final = asyncio.run(rows_snapshot(ids))
        assert final == before
        print(f"LEGACY SHA256 final={final} unchanged=1", flush=True)
        print("RESULT PASS full env.py chain and 0015 roundtrip", flush=True)
    finally:
        if created:
            asyncio.run(cleanup())


if __name__ == "__main__":
    main()
