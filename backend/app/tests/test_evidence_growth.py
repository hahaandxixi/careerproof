"""Real parser/report workflow on isolated material storage, never external AI."""

import asyncio
import io
import zipfile
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.models.analysis import AiUsageLog, AnalysisTask, MatchItem
from app.models.evidence_growth import EvidenceGrowthTask
from app.models.recruitment import Application, JobRequirement
from app.tests.test_real_matching import (
    create_job,
    match_report,
    matching_db,  # noqa: F401
    register,
    upload_materials,
)


def archive(code):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        output.writestr("main.py", code)
    return stream.getvalue()


def plan(report):
    return {
        "requirementId": report["items"][0]["requirementId"],
        "gapKind": "execution",
        "deliverable": "具名新版实现与运行结果样例",
        "steps": ["修正实现", "记录样例输出"],
        "acceptanceChecks": ["代码与结果样例可定位", "本人贡献仍需人工核对"],
    }


async def newer(student, project, code="def total(values):\n    return sum(values)\n"):
    response = await student.post(
        f"/api/v1/projects/{project['id']}/versions",
        data={"requestId": str(uuid4())},
        files={"file": ("补证-v2.zip", archive(code), "application/zip")},
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]["versionId"]


@pytest.mark.parametrize("scenario", ["implementation", "removed", "old_error", "requirement"])
async def test_uploaded_version_report_diff_and_frozen_enterprise_snapshot(
    matching_db,  # noqa: F811
    scenario,
):
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(hr, "growth-hr@example.com")
        job = await create_job(hr)
        await register(student, "growth-owner@example.com", "student")
        resume, project, version = await upload_materials(student)
        base = await match_report(student, job, resume, version)
        application = await student.post(
            "/api/v1/applications", json={"reportId": base["id"], "shareConsent": True}
        )
        assert application.status_code == 201, application.text
        app_id = application.json()["data"]["id"]
        original = (await hr.post(f"/api/v1/applications/{app_id}/view")).json()["data"]["report"]
        context_path = (
            f"/api/v1/match-reports/{base['id']}/enterprise-replies/"
            f"{base['items'][0]['requirementId']}"
        )
        assert (await student.get(context_path)).json()["data"] is None
        if scenario == "implementation":
            title = base["items"][0]["requirementTitle"]
            reply_text = f"【第1项：{title}】\n请用新版材料说明运行结果（合成）。"
            replied = await hr.post(
                f"/api/v1/applications/{app_id}/reply",
                json={
                    "kind": "continue",
                    "text": reply_text,
                    "references": [{
                        "requirementId": base["items"][0]["requirementId"],
                        "citationIds": [],
                    }],
                },
            )
            assert replied.status_code == 200, replied.text
            context = (await student.get(context_path)).json()["data"]
            assert context["applicationId"] == app_id
            assert context["text"] == "请用新版材料说明运行结果（合成）。"
            assert context["citationIds"] == []
            assert (await hr.get(context_path)).status_code == 403
            assert (
                await student.get(
                    f"/api/v1/match-reports/{base['id']}/enterprise-replies/{uuid4()}"
                )
            ).status_code == 404
        created = await student.post(
            f"/api/v1/match-reports/{base['id']}/growth-tasks", json=plan(base)
        )
        assert created.status_code == 201, created.text
        task = created.json()["data"]
        assert task["enterpriseReply"] == (context if scenario == "implementation" else None)
        url = f"/api/v1/growth-tasks/{task['id']}"
        frozen_gap = task["gap"]
        if scenario == "old_error":
            async with factory() as session:
                item = await session.scalar(
                    select(MatchItem).where(MatchItem.report_id == UUID(base["id"]))
                )
                item.evidence_snapshot = {
                    **item.evidence_snapshot,
                    "requirementTitle": "后来修正的旧报告文字",
                }
                await session.commit()
        if scenario == "requirement":
            changed = await hr.patch(
                f"/api/v1/jobs/{job['id']}",
                json={
                    "requirements": [{"rawText": "需要SQL查询", "skillName": "SQL", "weight": 3}]
                },
            )
            # Production freezes requirements after reports exist. Exercise
            # historical/import drift only inside this disposable test DB.
            assert changed.status_code == 409, changed.text
            async with factory() as session:
                requirement = await session.get(JobRequirement, UUID(job["requirements"][0]["id"]))
                requirement.raw_text = "原要求修订后的Python实践"
                requirement.weight = 3
                await session.commit()
        selected = [] if scenario == "removed" else [await newer(student, project)]
        attached = await student.put(
            url + "/materials",
            json={"resumeVersionId": resume["versionId"], "projectVersionIds": selected},
        )
        assert attached.status_code == 200, attached.text
        assert attached.json()["data"]["status"] == "materials_selected"
        accepted = await student.post(url + "/analyze", json={"externalAiConsent": False})
        assert accepted.status_code == 202, accepted.text
        result = (await student.get(url)).json()["data"]
        assert result["status"] == "compared", result
        assert result["targetReportId"] != base["id"]
        assert result["gap"] == frozen_gap
        assert result["enterpriseReply"] == (
            context if scenario == "implementation" else None
        )
        comparison = result["comparison"]
        assert comparison["baseId"] == base["id"]
        assert "materials" in comparison["contextChanges"]
        if scenario == "requirement":
            assert "requirements" in comparison["contextChanges"]
        elif scenario == "removed":
            assert any(i["removedEvidence"] for i in comparison["items"])
        else:
            assert any(i["addedEvidence"] for i in comparison["items"])
        repeated = await student.post(url + "/analyze", json={"externalAiConsent": False})
        assert repeated.json()["data"]["analysisTaskId"] == result["analysisTaskId"]
        assert (
            await student.put(
                url + "/materials",
                json={"resumeVersionId": resume["versionId"], "projectVersionIds": []},
            )
        ).status_code == 409
        again = (await hr.post(f"/api/v1/applications/{app_id}/view")).json()["data"]["report"]
        assert again == original
        if scenario == "implementation":
            # New evidence never replaces an already authorized application.
            assert (
                await student.post(
                    "/api/v1/applications",
                    json={
                        "reportId": result["targetReportId"],
                        "shareConsent": True,
                    },
                )
            ).status_code == 409
            continuation = await student.post(
                f"/api/v1/match-reports/{result['targetReportId']}/growth-tasks",
                json=plan(
                    (await student.get(f"/api/v1/match-reports/{result['targetReportId']}")).json()[
                        "data"
                    ]
                ),
            )
            assert continuation.status_code == 201
            assert continuation.json()["data"]["baseReportId"] == result["targetReportId"]
            assert (
                await hr.post(f"/api/v1/applications/{app_id}/resume-download")
            ).status_code == 200
            student_notices = (await student.get("/api/v1/notifications")).json()["data"]
            assert student_notices["total"] == 4
            assert (
                await student.post(f"/api/v1/applications/{app_id}/withdraw")
            ).status_code == 200
            enterprise_notices = (await hr.get("/api/v1/notifications")).json()["data"]
            assert enterprise_notices["total"] == 2
            assert all(not notice["accessible"] for notice in enterprise_notices["items"])
            for notice in enterprise_notices["items"]:
                assert (
                    await hr.get(f"/api/v1/notifications/{notice['id']}/target")
                ).status_code == 404
            assert (await hr.get(f"/api/v1/applications/{app_id}")).status_code == 404
            assert (await student.get(url)).json()["data"]["status"] == "compared"
            assert (await student.get(context_path)).json()["data"] == context
            # A persisted reply link can become invalid through legacy data drift.
            # Re-read must then hide the question in both entry points.
            async with factory() as session:
                saved_reply = await session.get(Application, UUID(app_id))
                saved_reply.reply_references = [{
                    "requirementId": str(uuid4()),
                    "citationIds": [],
                }]
                await session.commit()
            assert (await student.get(context_path)).json()["data"] is None
            assert (await student.get(url)).json()["data"]["enterpriseReply"] is None
        assert (await hr.get(url)).status_code == 403
        async with factory() as session:
            saved = await session.get(Application, UUID(app_id))
            assert saved.report_snapshot == original
            assert await session.scalar(select(func.count(AiUsageLog.id))) == 0
            assert await session.scalar(select(func.count(EvidenceGrowthTask.id))) == (
                2 if scenario == "implementation" else 1
            )


async def test_private_scope_idempotency_validation_and_same_content_stop(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
        AsyncClient(transport=transport, base_url="http://test") as other,
    ):
        await register(hr, "growth-scope-hr@example.com")
        job = await create_job(hr)
        await register(student, "growth-scope-owner@example.com", "student")
        await register(other, "growth-scope-other@example.com", "student")
        resume, project, version = await upload_materials(student)
        base = await match_report(student, job, resume, version)
        endpoint = f"/api/v1/match-reports/{base['id']}/growth-tasks"
        assert (await other.post(endpoint, json=plan(base))).status_code == 404
        assert (await hr.post(endpoint, json=plan(base))).status_code == 403
        assert (
            await student.post(endpoint, json={**plan(base), "requirementId": str(uuid4())})
        ).status_code == 404
        for patch in (
            {"steps": []},
            {"deliverable": " "},
            {"acceptanceChecks": ["x"] * 6},
            {"targetReportId": str(uuid4())},
        ):
            assert (await student.post(endpoint, json={**plan(base), **patch})).status_code == 422
        lookup = endpoint + "/" + plan(base)["requirementId"]
        assert (await student.get(lookup)).json()["data"] is None
        assert (await other.get(lookup)).status_code == 404
        assert (await hr.get(lookup)).status_code == 403
        first = (await student.post(endpoint, json=plan(base))).json()["data"]
        assert (await student.get(lookup)).json()["data"]["id"] == first["id"]
        second = (
            await student.post(endpoint, json={**plan(base), "deliverable": "不能覆盖原交付"})
        ).json()["data"]
        assert first["id"] == second["id"] and first["plan"] == second["plan"]
        url = f"/api/v1/growth-tasks/{first['id']}"
        assert (await other.get(url)).status_code == 404
        assert (
            await other.put(url + "/materials", json={"resumeVersionId": resume["versionId"]})
        ).status_code == 404
        assert (
            await student.post(url + "/analyze", json={"externalAiConsent": 1})
        ).status_code == 422
        assert (await student.post(url + "/analyze", json={})).status_code == 409
        same = await student.put(
            url + "/materials",
            json={
                "resumeVersionId": resume["versionId"],
                "projectVersionIds": [version["versionId"]],
            },
        )
        assert same.status_code == 409
        others_resume, _, _ = await upload_materials(other)
        assert (
            await student.put(
                url + "/materials", json={"resumeVersionId": others_resume["versionId"]}
            )
        ).status_code == 404
        async with factory() as session:
            assert await session.scalar(select(func.count(EvidenceGrowthTask.id))) == 1
            assert await session.scalar(select(func.count(AiUsageLog.id))) == 0


async def test_failed_analysis_is_preserved_and_never_automatically_retried(
    matching_db,  # noqa: F811
    monkeypatch,
):
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(hr, "growth-failure-hr@example.com")
        job = await create_job(hr)
        await register(student, "growth-failure-owner@example.com", "student")
        resume, project, version = await upload_materials(student)
        base = await match_report(student, job, resume, version)
        created = (
            await student.post(f"/api/v1/match-reports/{base['id']}/growth-tasks", json=plan(base))
        ).json()["data"]
        url = f"/api/v1/growth-tasks/{created['id']}"
        updated = await newer(student, project)
        await student.put(
            url + "/materials",
            json={"resumeVersionId": resume["versionId"], "projectVersionIds": [updated]},
        )
        calls = []

        async def failure(*args, **kwargs):
            calls.append(True)
            raise RuntimeError("isolated synthetic failure")

        monkeypatch.setattr("app.services.analysis.run_isolated", failure)
        assert (await student.post(url + "/analyze", json={})).status_code == 202
        result = (await student.get(url)).json()["data"]
        assert result["status"] == "analysis_failed" and result["comparison"] is None
        for _ in range(2):
            assert (await student.post(url + "/analyze", json={})).status_code == 409
        assert len(calls) == 1
        async with factory() as session:
            failed_id = UUID(result["analysisTaskId"])
            assert (await session.get(AnalysisTask, failed_id)).status.value == "failed"


async def test_postgres_concurrent_create_and_analysis_share_one_bound_task(
    matching_db,  # noqa: F811
    monkeypatch,
):
    app, factory = matching_db
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL row-lock concurrency requires the integration database")
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(hr, "growth-race-hr@example.com")
        job = await create_job(hr)
        await register(student, "growth-race-owner@example.com", "student")
        resume, project, version = await upload_materials(student)
        base = await match_report(student, job, resume, version)
        endpoint = f"/api/v1/match-reports/{base['id']}/growth-tasks"
        responses = await asyncio.gather(
            *(student.post(endpoint, json=plan(base)) for _ in range(3))
        )
        assert all(r.status_code == 201 for r in responses)
        ids = {r.json()["data"]["id"] for r in responses}
        assert len(ids) == 1
        url = f"/api/v1/growth-tasks/{ids.pop()}"
        updated = await newer(student, project)
        await student.put(
            url + "/materials",
            json={"resumeVersionId": resume["versionId"], "projectVersionIds": [updated]},
        )

        class DeferredRunner:
            def submit(self, *args):
                pass

        monkeypatch.setattr(
            "app.api.v1.evidence_growth.FastAPIBackgroundTaskRunner", DeferredRunner
        )
        responses = await asyncio.gather(
            *(student.post(url + "/analyze", json={}) for _ in range(3))
        )
        assert all(r.status_code == 202 for r in responses)
        assert len({r.json()["data"]["analysisTaskId"] for r in responses}) == 1
        async with factory() as session:
            assert await session.scalar(select(func.count(EvidenceGrowthTask.id))) == 1
            assert (
                await session.scalar(
                    select(func.count(AnalysisTask.id)).where(AnalysisTask.task_type == "job_match")
                )
                == 2
            )
