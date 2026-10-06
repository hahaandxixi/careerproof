"""Real row locks and migration for answer drafts, only inside the cp_test schema."""

import asyncio
from copy import deepcopy

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.tests.test_growth_answer import draft_payload, setup_answer_env
from app.tests.test_growth_answer_migration import migration
from app.tests.test_real_matching import matching_db  # noqa: F401


async def test_postgres_answer_draft_concurrent_first_create_admits_single_winner(matching_db):  # noqa: F811
    app, factory = matching_db
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires explicit PostgreSQL row locks")  # noqa: F821
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr)
        url = f"/api/v1/growth-tasks/{env['task']['id']}/answer-draft"
        responses = await asyncio.gather(
            student.put(url, json=draft_payload("并发甲", revision=0)),
            student.put(url, json=draft_payload("并发乙", revision=0)),
        )
        assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
        conflict = next(r for r in responses if r.status_code == 409)
        assert conflict.json()["code"] == 4240
        winner = next(r for r in responses if r.status_code == 200)
        assert winner.json()["data"]["revision"] == 1
        current = (await student.get(url)).json()["data"]
        assert current["revision"] == 1
        assert current["text"] in {"并发甲", "并发乙"}


async def test_postgres_answer_draft_concurrent_save_conflicts_on_same_revision(matching_db):  # noqa: F811
    app, factory = matching_db
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires explicit PostgreSQL row locks")  # noqa: F821
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr, "-same")
        url = f"/api/v1/growth-tasks/{env['task']['id']}/answer-draft"
        first = await student.put(url, json=draft_payload("基线草稿", revision=0))
        assert first.status_code == 200, first.text
        responses = await asyncio.gather(
            student.put(url, json=draft_payload("改甲", revision=1)),
            student.put(url, json=draft_payload("改乙", revision=1)),
            student.put(url, json=draft_payload("旧首建", revision=0)),
        )
        assert sorted(r.status_code for r in responses) == [200, 409, 409], [
            r.text for r in responses
        ]
        current = (await student.get(url)).json()["data"]
        assert current["revision"] == 2
        assert current["text"] in {"改甲", "改乙"}


async def test_postgres_answer_draft_migration_roundtrip_matches_model_schema(matching_db):  # noqa: F811
    app, factory = matching_db
    engine = factory.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires explicit PostgreSQL cp_test schema")  # noqa: F821
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr, "-migrate")
        url = f"/api/v1/growth-tasks/{env['task']['id']}/answer-draft"
        saved = await student.put(url, json=draft_payload("迁移前草稿", revision=0))
        assert saved.status_code == 200, saved.text
        module = migration("0015_growth_answer_drafts.py")
        query = text(
            'SELECT id,growth_task_id,text,"references",revision,created_at,updated_at '
            "FROM growth_answer_drafts"
        )
        task_query = text("SELECT * FROM evidence_growth_tasks")
        async with engine.begin() as connection:
            schema = await connection.scalar(text("SELECT current_schema()"))
            assert schema.startswith("cp_test_") and len(schema) == 40
            legacy = deepcopy((await connection.execute(task_query)).one()._mapping)

            def run(sync, direction):
                with Operations.context(MigrationContext.configure(sync)):
                    getattr(module, direction)()

            await connection.run_sync(lambda sync: run(sync, "downgrade"))
            assert (await connection.execute(task_query)).one()._mapping == legacy
            await connection.run_sync(lambda sync: run(sync, "upgrade"))
            assert (await connection.execute(task_query)).one()._mapping == legacy
            rows = (await connection.execute(query)).all()
            assert rows == []  # the dropped draft is gone; the table is usable again
        recreated = await student.put(url, json=draft_payload("迁移后重存", revision=0))
        assert recreated.status_code == 200, recreated.text
        assert recreated.json()["data"]["revision"] == 1
