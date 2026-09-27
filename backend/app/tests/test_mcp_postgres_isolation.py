"""Opt-in PostgreSQL grant isolation and revocation ordering, with synthetic reports.

SQLite cannot prove row-lock behavior. These tests use matching_db's disposable
schema only when CAREERPROOF_TEST_DATABASE_URL explicitly selects PostgreSQL.
No provider, production report, browser or external MCP client is used.
"""

import asyncio
import json
from collections import Counter
from contextlib import AsyncExitStack
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update

from app.core.database import get_session
from app.models.analysis import AnalysisTask, MatchReport
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.models.identity import User
from app.services import mcp_tools
from app.tests.test_jobs_api import job_payload, organization, register
from app.tests.test_real_matching import matching_db  # noqa: F401

ENDPOINT = "/api/v1/mcp-tools/invoke"
GRANTS = "/api/v1/mcp-tools/grants"


def invocation(report_id):
    return {"tool": "get_report_summary", "arguments": {"report_id": report_id}}


def authorization(grant):
    return {"Authorization": "Bearer " + grant["token"]}


@pytest.fixture
async def pg_world(matching_db):  # noqa: F811
    app, factory = matching_db
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires explicit local PostgreSQL test database and real row locks")
    tag = "cp_mcp_test_" + uuid4().hex

    async def sessions():
        async with factory() as session:
            # The fixture owns this pool and disposes it on teardown. A unique
            # application name identifies only our calls; never inspect SQL text.
            await session.execute(
                text("SELECT set_config('application_name', :tag, false)"), {"tag": tag}
            )
            yield session

    app.dependency_overrides[get_session] = sessions
    async with AsyncExitStack() as stack:
        clients = [
            await stack.enter_async_context(
                AsyncClient(transport=ASGITransport(app=app), base_url="http://synthetic")
            )
            for _ in range(3)
        ]
        employer, first, second = clients
        await register(employer, uuid4().hex + "@example.com")
        org = await organization(employer, name="合成MCP并发企业")
        created = await employer.post("/api/v1/jobs", json=job_payload(org))
        assert created.status_code == 201
        job = created.json()["data"]
        owners = [
            await register(client, uuid4().hex + "@example.com", "student")
            for client in (first, second)
        ]
        reports, markers = [], []
        async with factory() as session:
            for index in range(4):
                owner = owners[index // 2]
                task = AnalysisTask(created_by=UUID(owner["id"]), task_type="job_match")
                session.add(task)
                await session.flush()
                marker = "synthetic-mcp-private-report-" + str(index)
                report = MatchReport(
                    analysis_task_id=task.id,
                    job_id=UUID(job["id"]),
                    candidate_ref=owner["id"],
                    summary=marker,
                )
                session.add(report)
                await session.flush()
                reports.append(str(report.id))
                markers.append(marker)
            await session.commit()
        grants = []
        for index, report_id in enumerate(reports):
            response = await (first, second)[index // 2].post(
                GRANTS,
                json={
                    "report_ids": [report_id],
                    "external_client_consent": True,
                },
            )
            assert response.status_code == 200
            grants.append(response.json()["data"])
        try:
            yield {
                "clients": (first, second),
                "owners": owners,
                "reports": reports,
                "markers": markers,
                "grants": grants,
                "factory": factory,
                "tag": tag,
            }
        finally:
            # Restore only our generated identities so fixture cleanup can revoke
            # grants after account-state tests; the disposable schema is dropped.
            async with factory() as session:
                await session.execute(
                    update(User)
                    .where(User.id.in_([UUID(owner["id"]) for owner in owners]))
                    .values(is_active=True, role=UserRole.STUDENT)
                )
                await session.commit()
            for index, grant in enumerate(grants):
                response = await (first, second)[index // 2].delete(GRANTS + "/" + grant["grantId"])
                assert response.status_code == 200


async def wait_for_revocation_lock(world, blocker_pid):
    deadline = asyncio.get_running_loop().time() + 5
    async with world["factory"]() as session:
        while asyncio.get_running_loop().time() < deadline:
            await session.execute(text("SELECT pg_stat_clear_snapshot()"))
            waiting = await session.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                    "WHERE application_name = :tag AND wait_event_type = 'Lock' "
                    "AND pg_blocking_pids(pid) @> ARRAY[CAST(:blocker AS integer)])"
                ),
                {"tag": world["tag"], "blocker": blocker_pid},
            )
            if waiting:
                return True
            await asyncio.sleep(0.05)
    return False


async def test_postgres_pending_revocation_does_not_block_other_grants(pg_world, monkeypatch):
    world = pg_world
    first, second = world["clients"]
    grants, reports = world["grants"], world["reports"]
    started, release = asyncio.Event(), asyncio.Event()
    blocker_pid = None
    original_dispatch = mcp_tools.dispatch

    async def held_dispatch(session, user, tool, args):
        nonlocal blocker_pid
        if str(args.report_id) == reports[0]:
            blocker_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            started.set()
            await asyncio.wait_for(release.wait(), timeout=15)
        return await original_dispatch(session, user, tool, args)

    monkeypatch.setattr(mcp_tools, "dispatch", held_dispatch)
    reading = asyncio.create_task(
        first.post(ENDPOINT, json=invocation(reports[0]), headers=authorization(grants[0]))
    )
    revoking = None
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        revoking = asyncio.create_task(first.delete(GRANTS + "/" + grants[0]["grantId"]))
        assert await wait_for_revocation_lock(world, blocker_pid)
        assert not revoking.done()
        # Same owner, different grant; other owner, different grant. Neither
        # waits for the held grant. A foreign revoke cannot alter that grant.
        responses = await asyncio.wait_for(
            asyncio.gather(
                first.post(ENDPOINT, json=invocation(reports[1]), headers=authorization(grants[1])),
                second.post(
                    ENDPOINT, json=invocation(reports[2]), headers=authorization(grants[2])
                ),
                second.delete(GRANTS + "/" + grants[0]["grantId"]),
                second.post(
                    ENDPOINT, json=invocation(reports[0]), headers=authorization(grants[2])
                ),
            ),
            timeout=5,
        )
        assert [response.status_code for response in responses] == [200, 200, 404, 404]
        assert responses[0].json()["data"]["result"]["reportId"] == reports[1]
        assert responses[1].json()["data"]["result"]["reportId"] == reports[2]
        assert all(world["markers"][0] not in response.text for response in responses)
        assert not revoking.done() and not reading.done()
    finally:
        release.set()
        pending = [task for task in (reading, revoking) if task is not None]
        results = await asyncio.wait_for(asyncio.gather(*pending), timeout=5)
    # The admitted read holds the lock and finishes before revoke commits.
    # We promise denial after the successful revoke, not retroactive cancellation.
    assert [response.status_code for response in results] == [200, 200]
    denied = await first.post(
        ENDPOINT, json=invocation(reports[0]), headers=authorization(grants[0])
    )
    assert denied.status_code == 401 and world["markers"][0] not in denied.text
    for index in (1, 2):
        response = await (first, second)[index // 2].post(
            ENDPOINT, json=invocation(reports[index]), headers=authorization(grants[index])
        )
        assert response.status_code == 200
    async with world["factory"]() as session:
        calls = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.action == "mcp.call", AuditLog.resource_id == grants[0]["grantId"]
                )
            )
        )
        assert Counter(row.details["status"] for row in calls) == {
            "completed": 1,
            "revoked_or_missing": 1,
        }
        assert all(str(row.actor_id) == world["owners"][0]["id"] for row in calls)


async def test_postgres_four_grants_have_independent_caps_and_private_audits(pg_world):
    world = pg_world
    grants, reports = world["grants"], world["reports"]
    clients = world["clients"]
    # Every grant pays one slot for a rejected foreign-report attempt.
    rejected = await asyncio.gather(
        *(
            clients[index // 2].post(
                ENDPOINT, json=invocation(reports[(index + 2) % 4]), headers=authorization(grant)
            )
            for index, grant in enumerate(grants)
        )
    )
    assert all(response.status_code == 404 for response in rejected)
    assert all("result" not in (response.json().get("data") or {}) for response in rejected)
    semaphore = asyncio.Semaphore(12)

    async def invoke(index):
        async with semaphore:
            return index, await clients[index // 2].post(
                ENDPOINT, json=invocation(reports[index]), headers=authorization(grants[index])
            )

    results = await asyncio.wait_for(
        asyncio.gather(*(invoke(index) for _ in range(47) for index in range(4))), timeout=30
    )
    for index in range(4):
        own_results = [response for group, response in results if group == index]
        assert Counter(response.status_code for response in own_results) == {200: 39, 429: 8}
        for response in own_results:
            if response.status_code == 200:
                result = response.json()["data"]["result"]
                assert result["reportId"] == reports[index]
                assert result["summary"] == world["markers"][index]
            else:
                assert "result" not in (response.json().get("data") or {})
            assert all(
                marker not in response.text
                for n, marker in enumerate(world["markers"])
                if n != index
            )
    async with world["factory"]() as session:
        for index, grant in enumerate(grants):
            calls = list(
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.action == "mcp.call", AuditLog.resource_id == grant["grantId"]
                    )
                )
            )
            assert len(calls) == 48
            assert Counter(row.details["status"] for row in calls) == {
                "completed": 39,
                "rejected": 1,
                "limit_rejected": 8,
            }
            assert all(str(row.actor_id) == world["owners"][index // 2]["id"] for row in calls)
            saved = json.dumps([row.details for row in calls])
            assert all(marker not in saved for marker in world["markers"])
            assert all(grant["token"] not in saved for grant in grants)
        saved_reports = list(await session.scalars(select(MatchReport)))
        assert {str(row.id): row.summary for row in saved_reports} == dict(
            zip(reports, world["markers"], strict=True)
        )


@pytest.mark.parametrize("fault", ["disabled", "role_changed"])
@pytest.mark.parametrize("stage", ["lock_wait", "after_dispatch"])
async def test_postgres_changed_identity_cannot_export_after_wait_or_read(
    pg_world, monkeypatch, fault, stage
):
    world = pg_world
    first = world["clients"][0]
    grant, report_id = world["grants"][0], world["reports"][0]
    pending = None

    async def change_identity():
        values = {"is_active": False} if fault == "disabled" else {"role": UserRole.ENTERPRISE}
        async with world["factory"]() as session:
            await session.execute(
                update(User).where(User.id == UUID(world["owners"][0]["id"])).values(**values)
            )
            await session.commit()

    if stage == "lock_wait":
        async with world["factory"]() as session, session.begin():
            await session.scalar(
                select(AuditLog)
                .where(AuditLog.action == "mcp.grant", AuditLog.resource_id == grant["grantId"])
                .with_for_update()
            )
            blocker_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            pending = asyncio.create_task(
                first.post(ENDPOINT, json=invocation(report_id), headers=authorization(grant))
            )
            try:
                assert await wait_for_revocation_lock(world, blocker_pid)
                await change_identity()
            except BaseException:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
                raise
        response = await asyncio.wait_for(pending, timeout=5)
    else:
        original_dispatch = mcp_tools.dispatch

        async def change_after_read(session, user, tool, args):
            result = await original_dispatch(session, user, tool, args)
            await change_identity()
            return result

        monkeypatch.setattr(mcp_tools, "dispatch", change_after_read)
        response = await first.post(
            ENDPOINT, json=invocation(report_id), headers=authorization(grant)
        )
    assert response.status_code == 401
    assert world["markers"][0] not in response.text
    assert "result" not in (response.json().get("data") or {})
    async with world["factory"]() as session:
        calls = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.action == "mcp.call", AuditLog.resource_id == grant["grantId"]
                )
            )
        )
        assert len(calls) == 1 and calls[0].details["status"] == "identity_rejected"
        assert calls[0].actor_id == UUID(world["owners"][0]["id"])
