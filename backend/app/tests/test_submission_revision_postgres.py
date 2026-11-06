"""Real PG lock ordering, opt-in synthetic schemas; never real business data."""
import asyncio
import contextvars
import os

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recruitment import Application, ApplicationEvent
from app.tests.test_submission_review_revision import consent_case as consent_case

pytest_plugins = ["app.tests.test_real_matching"]
pytestmark = pytest.mark.skipif(
    not os.environ.get("CAREERPROOF_TEST_DATABASE_URL", "").startswith("postgresql+asyncpg://"),
    reason="Requires an explicitly selected synthetic PostgreSQL database",
)


@pytest.fixture
async def jobs_db(matching_db):
    yield matching_db


@pytest.mark.parametrize("first", ["review", "submit"])
async def test_review_and_submission_have_one_serial_order(
    consent_case, monkeypatch, first,  # noqa: F811 - imported pytest fixture
):
    (hr, student, outsider, job, rid, resume, raw, factory), req, _ = consent_case
    operation = contextvars.ContextVar("operation", default="")
    ready, release = asyncio.Event(), asyncio.Event()
    original_commit = AsyncSession.commit

    async def gated_commit(session):
        if operation.get() == first:
            ready.set()
            await asyncio.wait_for(release.wait(), 10)
        return await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", gated_commit)

    async def invoke(kind):
        token = operation.set(kind)
        try:
            if kind == "review":
                return await student.patch(
                    f"/api/v1/match-reports/{rid}/items/{req}/review",
                    json={"status": "rejected", "note": "Synthetic concurrent correction"},
                )
            return await student.post("/api/v1/applications", json={
                "reportId": str(rid), "shareConsent": True, "expectedReviewRevision": 1,
            })
        finally:
            operation.reset(token)

    tasks = []
    try:
        first_task = asyncio.create_task(invoke(first))
        tasks.append(first_task)
        await asyncio.wait_for(ready.wait(), 10)
        other = "submit" if first == "review" else "review"
        second_task = asyncio.create_task(invoke(other))
        tasks.append(second_task)
        # Observe the DB lock wait itself, not a timing-only assumption.
        async with factory() as monitor:
            for _ in range(100):
                waiting = await monitor.scalar(text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                    "AND wait_event_type='Lock' AND query ILIKE '%match_reports%'"
                ))
                await monitor.rollback()  # refresh pg_stat_activity snapshot
                if waiting:
                    break
                await asyncio.sleep(.03)
            assert waiting, "Second real request never reached the expected PostgreSQL lock wait"
        assert not second_task.done()
        release.set()
        results = dict(zip(
            [first, other], await asyncio.wait_for(asyncio.gather(*tasks), 10), strict=True
        ))
        assert results["review"].status_code == 200, results["review"].text
        assert results["submit"].status_code == (409 if first == "review" else 201), (
            results["submit"].text
        )
        current = (await student.get(f"/api/v1/match-reports/{rid}")).json()["data"]
        assert current["reviewRevision"] == 2
        assert current["items"][0]["confirmationStatus"] == "rejected"
        async with factory() as session:
            rows = list(await session.scalars(select(Application)))
            if first == "review":
                assert rows == []
                assert await session.scalar(select(func.count()).select_from(ApplicationEvent)) == 0
            else:
                assert len(rows) == 1
                assert rows[0].report_snapshot["reviewRevision"] == 1
                assert rows[0].report_snapshot["items"][0]["confirmationStatus"] != "rejected"
        print(
            f"PG_LOCK_OBSERVED first={first}; "
            f"submit={results['submit'].status_code}; currentRevision=2"
        )
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
