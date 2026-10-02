"""Actual event transactions, recipient isolation and revocation; no model calls."""

import pytest
from sqlalchemy import func, select

from app.models.identity import EnterpriseMembership
from app.models.notification import Notification
from app.models.recruitment import Application, ApplicationEvent
from app.services.applications import ApplicationService
from app.tests.test_applications_api import close, setup

pytest_plugins = ["app.tests.test_jobs_api", "app.tests.test_real_matching"]


async def listing(client, suffix=""):
    response = await client.get("/api/v1/notifications" + suffix)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_real_events_dedup_pagination_read_scope_and_revocation(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        for _ in range(2):
            response = await student.post(
                "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
            )
            assert response.status_code == 201
        aid = response.json()["data"]["id"]
        assert (await listing(student))["unreadCount"] == 1
        enterprise_notice = (await listing(hr))["items"][0]
        assert enterprise_notice["title"] == "收到一份新的授权投递"
        assert set(enterprise_notice) == {
            "id",
            "type",
            "title",
            "createdAt",
            "readAt",
            "accessible",
        }
        assert (await listing(other))["total"] == 0
        nid = enterprise_notice["id"]
        for path, method in [(f"/{nid}/read", "post"), (f"/{nid}/target", "get")]:
            assert (await getattr(other, method)("/api/v1/notifications" + path)).status_code == 404
        for _ in range(2):
            assert (await hr.post(f"/api/v1/applications/{aid}/view")).status_code == 200
            assert (await hr.post(f"/api/v1/applications/{aid}/resume-download")).status_code == 200
        assert (
            await hr.post(
                f"/api/v1/applications/{aid}/reply",
                json={"kind": "continue", "text": "PRIVATE REPLY"},
            )
        ).status_code == 200
        result = await listing(student, "?page_size=2")
        assert result["total"] == 4 and len(result["items"]) == 2 and result["unreadCount"] == 4
        assert "PRIVATE REPLY" not in str(result)
        assert (await listing(student, "?page=2&page_size=2"))["items"][0]["id"] != result["items"][
            0
        ]["id"]
        student_nid = result["items"][0]["id"]
        target = (await student.get(f"/api/v1/notifications/{student_nid}/target")).json()["data"]
        assert target["href"] == f"/applications#application-{aid}"
        for _ in range(2):
            assert (await student.post(f"/api/v1/notifications/{student_nid}/read")).json()["data"][
                "unreadCount"
            ] == 3
        assert (await listing(student, "?unread_only=true"))["total"] == 3
        assert (await listing(hr))["total"] == 1  # Own view/download/reply do not notify HR.
        assert (await student.post("/api/v1/notifications/read-all")).json()["data"][
            "unreadCount"
        ] == 0
        for _ in range(2):
            assert (await student.post(f"/api/v1/applications/{aid}/withdraw")).status_code == 200
        assert (await listing(student))["unreadCount"] == 1
        enterprise = await listing(hr)
        assert enterprise["total"] == 2
        assert all(not row["accessible"] for row in enterprise["items"])
        assert all("撤回或当前" in row["title"] for row in enterprise["items"])
        assert (await hr.get(f"/api/v1/notifications/{nid}/target")).status_code == 404
        assert (await hr.post(f"/api/v1/notifications/{nid}/read")).status_code == 200
        assert (await student.get("/api/v1/notifications?page=0")).status_code == 422
        assert (await student.get("/api/v1/notifications?page_size=51")).status_code == 422
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(ApplicationEvent)) == 5
            assert await session.scalar(select(func.count()).select_from(Notification)) == 7
    finally:
        await close(hr, student, other)


async def test_transaction_rollback_leaves_no_event_or_notification(jobs_db, tmp_path, monkeypatch):
    hr, student, other, _job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    from app.services import applications

    async def fail(*_args):
        raise RuntimeError("synthetic transactional notification failure")

    monkeypatch.setattr(applications, "notify_application_event", fail)
    from app.models.identity import User
    from app.schemas.applications import ApplicationCreate

    async with factory() as session:
        owner = await session.scalar(select(User).where(User.email == "student@example.com"))
        with pytest.raises(RuntimeError):
            await ApplicationService(session).create(
                ApplicationCreate(report_id=rid, share_consent=True), owner
            )
        await session.rollback()
    async with factory() as session:
        for model in (Application, ApplicationEvent, Notification):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
    await close(hr, student, other)


async def test_membership_loss_rechecks_old_notice_without_leaking_details(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, _job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        await student.post(
            "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
        )
        nid = (await listing(hr))["items"][0]["id"]
        assert (await hr.get(f"/api/v1/notifications/{nid}/target")).status_code == 200
        async with factory() as session:
            membership = await session.scalar(select(EnterpriseMembership))
            membership.is_active = False
            await session.commit()
        assert not (await listing(hr))["items"][0]["accessible"]
        assert (await hr.get(f"/api/v1/notifications/{nid}/target")).status_code == 404
    finally:
        await close(hr, student, other)


async def test_postgres_concurrent_view_deduplicates_event_and_notice(
    matching_db, tmp_path, monkeypatch
):
    import asyncio

    if matching_db[1].kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL row lock integration only")
    hr, student, other, _job, rid, _resume, _raw, factory = await setup(
        matching_db, tmp_path, monkeypatch
    )
    try:
        response = await student.post(
            "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
        )
        aid = response.json()["data"]["id"]
        responses = await asyncio.gather(
            *[hr.post(f"/api/v1/applications/{aid}/view") for _ in range(4)]
        )
        assert all(r.status_code == 200 for r in responses)
        assert (await listing(student))["unreadCount"] == 2
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(ApplicationEvent)) == 2
            assert await session.scalar(select(func.count()).select_from(Notification)) == 3
    finally:
        await close(hr, student, other)


async def test_authorized_target_detail_is_read_only_and_last_page_recovers(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, _job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        response = await student.post(
            "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
        )
        aid = response.json()["data"]["id"]
        for actor in (student, hr):
            detail = await actor.get(f"/api/v1/applications/{aid}")
            assert detail.status_code == 200
            assert detail.json()["data"]["id"] == aid and "report" not in detail.json()["data"]
        assert (await other.get(f"/api/v1/applications/{aid}")).status_code == 404
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(ApplicationEvent)) == 1
            assert await session.scalar(select(func.count()).select_from(Notification)) == 2
        await hr.post(f"/api/v1/applications/{aid}/view")
        second = await listing(student, "?page=2&page_size=1&unread_only=true")
        assert second["page"] == 2 and second["total"] == 2
        await student.post(f"/api/v1/notifications/{second['items'][0]['id']}/read")
        recovered = await listing(student, "?page=2&page_size=1&unread_only=true")
        assert recovered["page"] == 1 and len(recovered["items"]) == 1
        await student.post("/api/v1/notifications/read-all")
        empty = await listing(student, "?page=99&unread_only=true")
        assert empty["page"] == 1 and empty["total"] == 0
        await student.post(f"/api/v1/applications/{aid}/withdraw")
        assert (await hr.get(f"/api/v1/applications/{aid}")).status_code == 404
        assert (await student.get(f"/api/v1/applications/{aid}")).status_code == 200
    finally:
        await close(hr, student, other)
