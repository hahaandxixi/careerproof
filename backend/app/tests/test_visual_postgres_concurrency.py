"""Real PostgreSQL account-lock/cache integration with synthetic provider output.

Opt in with CAREERPROOF_TEST_DATABASE_URL. The shared matching fixture creates
and drops only its generated cp_test_* schema. No production images or API calls.
"""

import asyncio
import hashlib
import io
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import select, text

from app.agents.contracts import ModelUsage
from app.core.config import settings
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.portfolio import ProjectVersion
from app.services.visual_evidence import _daily_ai_budget
from app.tests.test_jobs_api import register
from app.tests.test_real_matching import matching_db  # noqa: F401
from app.tests.test_visual_evidence import image_version, visual_answer


@pytest.mark.parametrize("same_version", [True, False])
@pytest.mark.parametrize("first_failure", [True, False])
async def test_postgres_visual_cache_recheck_after_observed_account_lock(
    matching_db,  # noqa: F811
    monkeypatch,
    same_version,
    first_failure,
):
    app, factory = matching_db
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires an explicitly configured isolated PostgreSQL schema")
    monkeypatch.setattr(settings, "ai_daily_report_limit", 1)
    entered = asyncio.Event()
    release = asyncio.Event()
    second_at_budget = asyncio.Event()
    pids = []
    calls = []

    async def budget_probe(session, user_id):
        # Wrap the actual service, never replace its row lock or budget calculation.
        pids.append(await session.scalar(text("SELECT pg_backend_pid()")))
        if len(pids) == 2:
            second_at_budget.set()
        return await _daily_ai_budget(session, user_id)

    class Provider:
        name = "synthetic"
        model = "synthetic-no-network"

        async def observe(self, _bytes):
            calls.append(1)
            entered.set()
            await asyncio.wait_for(release.wait(), timeout=15)
            if first_failure and len(calls) == 1:
                raise ValueError("Synthetic invalid first output")
            return visual_answer()

        def combined_usage(self):
            return ModelUsage(input_tokens=17, output_tokens=13, latency_ms=1)

    monkeypatch.setattr("app.services.visual_evidence._daily_ai_budget", budget_probe)
    monkeypatch.setattr("app.services.visual_evidence.get_vision_provider", lambda: Provider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "pg-visual-concurrency@example.com", "student")
        first_version = await image_version(factory, UUID(user["id"]), "pg-first.png")
        second_version = first_version
        if not same_version:
            second_version = await image_version(factory, UUID(user["id"]), "pg-second.png")
            # Set up different pixels before either version has any observation.
            raw = io.BytesIO()
            Image.new("RGB", (100, 80), "black").save(raw, format="PNG")
            (settings.storage_base_dir / second_version.archive_storage_key).write_bytes(
                raw.getvalue()
            )
            async with factory() as session:
                version = await session.get(ProjectVersion, second_version.id)
                version.content_hash = hashlib.sha256(raw.getvalue()).hexdigest()
                await session.commit()
        first = asyncio.create_task(
            client.post(
                f"/api/v1/project-versions/{first_version.id}/visual-review",
                json={"externalImageConsent": True},
            )
        )
        second = None
        observed = False
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            second = asyncio.create_task(
                client.post(
                    f"/api/v1/project-versions/{second_version.id}/visual-review",
                    json={"externalImageConsent": True},
                )
            )
            await asyncio.wait_for(second_at_budget.wait(), timeout=10)
            async with factory() as observer, asyncio.timeout(5):
                while not observed:
                    # Refresh statistics, and identify the actual blocker instead
                    # of pg_stat_activity.query text or any unrelated row lock.
                    await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                    observed = bool(
                        await observer.scalar(
                            text(
                                "SELECT wait_event_type = 'Lock' AND "
                                ":blocker = ANY(pg_blocking_pids(pid)) "
                                "FROM pg_stat_activity WHERE pid = :waiter"
                            ),
                            {"blocker": pids[0], "waiter": pids[1]},
                        )
                    )
                    if not observed:
                        await asyncio.sleep(0.01)
            assert not first.done() and not second.done()
        finally:
            release.set()
            pending = [first] + ([second] if second is not None else [])
            results = await asyncio.wait_for(asyncio.gather(*pending), timeout=10)
        assert observed, "The second request must demonstrably wait on the first account lock"
        assert len(pids) == 2 and len(calls) == 1
        first_result, second_result = results
        assert first_result.status_code == 200, first_result.text
        if same_version:
            assert second_result.status_code == 200, second_result.text
            assert first_result.json()["data"]["id"] == second_result.json()["data"]["id"]
            assert second_result.json()["data"]["status"] == (
                "unavailable" if first_failure else "completed"
            )
        else:
            assert second_result.status_code == 429, second_result.text
        async with factory() as session:
            tasks = list(await session.scalars(select(AnalysisTask)))
            usage = list(await session.scalars(select(AiUsageLog)))
            assert len(tasks) == 1 and tasks[0].task_type == "visual_review"
            assert len(usage) == 1 and usage[0].input_tokens == 17 and usage[0].output_tokens == 13

        if same_version and first_failure:
            # A new explicit request after the shared failure can retry, within
            # budget. The coalesced failure must not become a permanent cache.
            monkeypatch.setattr(settings, "ai_daily_report_limit", 2)
            retried = await client.post(
                f"/api/v1/project-versions/{first_version.id}/visual-review",
                json={"externalImageConsent": True},
            )
            assert retried.status_code == 200, retried.text
            assert retried.json()["data"]["status"] == "completed"
            assert retried.json()["data"]["id"] != first_result.json()["data"]["id"]
            assert len(calls) == 2
            async with factory() as session:
                assert len(list(await session.scalars(select(AnalysisTask)))) == 2
                assert len(list(await session.scalars(select(AiUsageLog)))) == 2
