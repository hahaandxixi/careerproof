"""Student-private answer drafts on real report workflow, never external AI."""

from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.evidence_growth import EvidenceGrowthTask
from app.models.recruitment import ApplicationEvent
from app.tests.test_evidence_growth import newer, plan
from app.tests.test_real_matching import (
    create_job,
    match_report,
    matching_db,  # noqa: F401
    register,
    source_archive,
    upload_materials,
)


def draft_payload(text="我的私人回答草稿", revision=0, references=None):
    return {
        "text": text,
        "references": [] if references is None else references,
        "expectedRevision": revision,
    }


def ref(report_id, requirement_id, citation_id):
    return {
        "reportId": report_id,
        "requirementId": requirement_id,
        "citationId": citation_id,
    }


async def setup_answer_env(student, hr, suffix=""):
    """Register an enterprise job, one student, real report and a growth task."""
    await register(hr, f"answer-hr{suffix}@example.com")
    job = await create_job(hr)
    await register(student, f"answer-student{suffix}@example.com", "student")
    resume, project, version = await upload_materials(student)
    base = await match_report(student, job, resume, version)
    created = await student.post(
        f"/api/v1/match-reports/{base['id']}/growth-tasks", json=plan(base)
    )
    assert created.status_code == 201, created.text
    return {
        "base": base,
        "task": created.json()["data"],
        "resume": resume,
        "project": project,
        "version": version,
    }


def base_citation(env):
    evidence = env["base"]["items"][0]["evidenceList"]
    citation = next(e["citationId"] for e in evidence if e.get("citationId"))
    return citation


async def upload_reference_version(student, project):
    """A declared third-party reference version; its citations stay marked as reference."""
    response = await student.post(
        f"/api/v1/projects/{project['id']}/versions",
        data={"requestId": str(uuid4()), "materialRole": "reference"},
        files={"file": ("第三方示例-v2.zip", source_archive(), "application/zip")},
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]["versionId"]


async def complete_same_job_target(student, env):
    """Select declared third-party materials against the base job and finish the analysis."""
    version_id = await upload_reference_version(student, env["project"])
    url = f"/api/v1/growth-tasks/{env['task']['id']}"
    attached = await student.put(
        url + "/materials",
        json={"resumeVersionId": env["resume"]["versionId"], "projectVersionIds": [version_id]},
    )
    assert attached.status_code == 200, attached.text
    accepted = await student.post(url + "/analyze", json={"externalAiConsent": False})
    assert accepted.status_code == 202, accepted.text
    data = (await student.get(url)).json()["data"]
    assert data["status"] == "compared", data
    target = (await student.get(f"/api/v1/match-reports/{data['targetReportId']}")).json()["data"]
    return data, target


async def test_answer_draft_create_update_clear_and_refresh_read(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr)
        task, base = env["task"], env["base"]
        url = f"/api/v1/growth-tasks/{task['id']}/answer-draft"
        assert (await student.get(url)).json()["data"] is None

        text = "第一行\n第二行  保留缩进\n结尾"
        created = await student.put(url, json=draft_payload(text=text, revision=0))
        assert created.status_code == 200, created.text
        draft = created.json()["data"]
        assert draft["taskId"] == task["id"]
        assert draft["requirementId"] == task["requirementId"]
        assert draft["text"] == text  # newlines and spacing kept verbatim
        assert draft["references"] == []
        assert draft["revision"] == 1
        assert draft["updatedAt"]
        assert "仅本人" in draft["boundary"]

        reread = (await student.get(url)).json()["data"]
        assert reread == draft  # refresh returns the identical saved draft

        citation = base_citation(env)
        updated = await student.put(
            url,
            json={
                "text": "更新后草稿",
                "references": [ref(base["id"], task["requirementId"], citation)],
                "expectedRevision": 1,
            },
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()["data"]
        assert body["revision"] == 2 and body["text"] == "更新后草稿"
        saved_ref = body["references"][0]
        assert saved_ref["available"] is True
        assert saved_ref["reportId"] == base["id"]
        assert saved_ref["requirementId"] == task["requirementId"]
        assert saved_ref["citationId"] == citation
        # Original text, file location and provenance are read from the frozen report.
        assert saved_ref["snippet"]
        assert saved_ref["filePath"]
        assert saved_ref["provenance"] in {"portfolio", "reference"}

        cleared = await student.put(url, json=draft_payload(text="", revision=2))
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["data"]["revision"] == 3
        assert cleared.json()["data"]["text"] == ""
        assert cleared.json()["data"]["references"] == []
        # 刷新读取必须与第三次保存回执完全对齐（revision/updatedAt/引用一致）。
        assert (await student.get(url)).json()["data"] == cleared.json()["data"]


async def test_answer_draft_revision_guards_reject_conflicting_saves(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr, "-guard")
        url = f"/api/v1/growth-tasks/{env['task']['id']}/answer-draft"

        stale_first = await student.put(url, json=draft_payload("早写", revision=1))
        assert stale_first.status_code == 409, stale_first.text
        assert stale_first.json()["code"] == 4240

        first = await student.put(url, json=draft_payload("首次保存", revision=0))
        assert first.status_code == 200, first.text
        assert first.json()["data"]["revision"] == 1

        replay = await student.put(url, json=draft_payload("重放", revision=0))
        assert replay.status_code == 409, replay.text

        update = await student.put(url, json=draft_payload("第二版", revision=1))
        assert update.status_code == 200, update.text
        assert update.json()["data"]["revision"] == 2

        stale = await student.put(url, json=draft_payload("过期写入", revision=1))
        assert stale.status_code == 409, stale.text
        assert stale.json()["code"] == 4240
        current = (await student.get(url)).json()["data"]
        assert current["text"] == "第二版" and current["revision"] == 2  # 新版本未被覆盖

        fresh = await student.put(url, json=draft_payload("第三版", revision=2))
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()["data"]["revision"] == 3


async def test_answer_draft_is_private_to_its_owner(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
        AsyncClient(transport=transport, base_url="http://test") as stranger,
    ):
        env = await setup_answer_env(student, hr, "-private")
        url = f"/api/v1/growth-tasks/{env['task']['id']}/answer-draft"
        saved = await student.put(url, json=draft_payload("仅本人可见", revision=0))
        assert saved.status_code == 200, saved.text

        assert (await hr.get(url)).status_code == 403
        assert (await hr.put(url, json=draft_payload(revision=0))).status_code == 403
        options_url = f"/api/v1/growth-tasks/{env['task']['id']}/answer-draft/references"
        assert (await hr.get(options_url)).status_code == 403

        await register(stranger, "answer-stranger@example.com", "student")
        assert (await stranger.get(url)).status_code == 404
        assert (await stranger.put(url, json=draft_payload(revision=0))).status_code == 404
        assert (await stranger.get(options_url)).status_code == 404
        guessed = f"/api/v1/growth-tasks/{uuid4()}/answer-draft"
        assert (await stranger.get(guessed)).status_code == 404
        assert (await stranger.put(guessed, json=draft_payload(revision=0))).status_code == 404
        # The owner still reads the draft, strangers never saw it.
        assert ((await student.get(url)).json()["data"])["text"] == "仅本人可见"


async def test_answer_draft_accepts_real_base_and_target_citations(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr, "-target")
        task, base = env["task"], env["base"]
        result, target = await complete_same_job_target(student, env)
        target_item = next(
            i for i in target["items"] if i["requirementId"] == task["requirementId"]
        )
        target_citation = next(
            e["citationId"] for e in target_item["evidenceList"] if e.get("citationId")
        )
        url = f"/api/v1/growth-tasks/{task['id']}/answer-draft"
        payload = {
            "text": "带真实引用的草稿",
            "references": [
                ref(base["id"], task["requirementId"], base_citation(env)),
                ref(target["id"], task["requirementId"], target_citation),
            ],
            "expectedRevision": 0,
        }
        saved = await student.put(url, json=payload)
        assert saved.status_code == 200, saved.text
        body = saved.json()["data"]
        assert body["revision"] == 1 and len(body["references"]) == 2
        # 基准材料来自本人作品集；对照材料是声明为第三方的参考版本。
        assert body["references"][0]["provenance"] == "portfolio"
        assert body["references"][1]["provenance"] == "reference"  # 第三方来源仍标参考
        for saved_ref in body["references"]:
            assert saved_ref["available"] is True
            assert saved_ref["snippet"] and saved_ref["filePath"]
            assert saved_ref["provenance"] in {"portfolio", "reference"}

        reread = (await student.get(url)).json()["data"]
        assert reread["references"] == body["references"]


async def test_answer_draft_reference_options_track_completed_target(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr, "-options")
        task, base = env["task"], env["base"]
        options_url = f"/api/v1/growth-tasks/{task['id']}/answer-draft/references"

        # Readable before any draft exists; only the frozen baseline is listed.
        empty_draft = await student.get(f"/api/v1/growth-tasks/{task['id']}/answer-draft")
        assert empty_draft.json()["data"] is None
        before = await student.get(options_url)
        assert before.status_code == 200, before.text
        options = before.json()["data"]
        assert options, "基准报告应提供可引用条目"
        assert all(option["reportKind"] == "base" for option in options)
        base_item = next(i for i in base["items"] if i["requirementId"] == task["requirementId"])
        assert {o["citationId"] for o in options} == {
            e["citationId"] for e in base_item["evidenceList"] if e.get("citationId")
        }

        result, target = await complete_same_job_target(student, env)
        after = (await student.get(options_url)).json()["data"]
        target_item = next(
            i for i in target["items"] if i["requirementId"] == task["requirementId"]
        )
        target_options = [o for o in after if o["reportKind"] == "target"]
        base_options = [o for o in after if o["reportKind"] == "base"]
        assert base_options and target_options
        assert {o["citationId"] for o in target_options} == {
            e["citationId"] for e in target_item["evidenceList"] if e.get("citationId")
        }
        assert any(o["provenance"] == "reference" for o in target_options)
        for option in after:
            assert option["reportId"] in {base["id"], result["targetReportId"]}
            assert option["requirementId"] == task["requirementId"]
            assert option["filePath"] and option["provenance"] in {"portfolio", "reference"}
            assert isinstance(option["lineStart"], int) and isinstance(option["lineEnd"], int)


async def test_answer_draft_rejects_forged_or_mismatched_references(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
        AsyncClient(transport=transport, base_url="http://test") as stranger,
    ):
        env = await setup_answer_env(student, hr, "-forge")
        task, base = env["task"], env["base"]
        url = f"/api/v1/growth-tasks/{task['id']}/answer-draft"
        saved = await student.put(url, json=draft_payload("拒绝前基线", revision=0))
        assert saved.status_code == 200, saved.text

        stranger_env = await setup_answer_env(stranger, hr, "-forge-b")
        stranger_report = stranger_env["base"]["id"]

        citation = base_citation(env)
        rejects = [
            ("未知报告", [ref(str(uuid4()), task["requirementId"], citation)]),
            ("他人报告", [ref(stranger_report, task["requirementId"], citation)]),
            ("伪造引用编号", [ref(base["id"], task["requirementId"], "FAKE-CITATION")]),
            ("要求不符", [ref(base["id"], str(uuid4()), citation)]),
            ("完全重复", [ref(base["id"], task["requirementId"], citation)] * 2),
            ("超过20条", [ref(base["id"], task["requirementId"], citation)] * 21),
        ]
        for label, references in rejects:
            rejected = await student.put(
                url,
                json={"text": "不应写入", "references": references, "expectedRevision": 1},
            )
            assert rejected.status_code == 422, (label, rejected.text)
        current = (await student.get(url)).json()["data"]
        assert current["text"] == "拒绝前基线" and current["revision"] == 1
        assert current["references"] == []

        # Same skill name on a different job cannot impersonate the original question.
        cross = await create_job(hr, skills=("Python",))
        version_id = await newer(student, env["project"])
        attached = await student.put(
            f"/api/v1/growth-tasks/{task['id']}/materials",
            json={
                "resumeVersionId": env["resume"]["versionId"],
                "projectVersionIds": [version_id],
                "targetJobId": cross["id"],
            },
        )
        assert attached.status_code == 200, attached.text
        accepted = await student.post(
            f"/api/v1/growth-tasks/{task['id']}/analyze", json={"externalAiConsent": False}
        )
        assert accepted.status_code == 202, accepted.text
        task_view = (await student.get(f"/api/v1/growth-tasks/{task['id']}")).json()["data"]
        cross_report = task_view["targetReportId"]
        cross_item = next(
            i
            for i in (await student.get(f"/api/v1/match-reports/{cross_report}")).json()["data"][
                "items"
            ]
            if i["skill"] == "Python"
        )
        cross_citation = next(
            e["citationId"] for e in cross_item["evidenceList"] if e.get("citationId")
        )
        impersonated = await student.put(
            url,
            json={
                "text": "跨岗位冒充",
                "references": [ref(cross_report, task["requirementId"], cross_citation)],
                "expectedRevision": 1,
            },
        )
        assert impersonated.status_code == 422, impersonated.text
        # The cross-job completed report lacks the original requirement, so the
        # selectable list keeps offering only the frozen baseline options.
        options = (
            await student.get(f"/api/v1/growth-tasks/{task['id']}/answer-draft/references")
        ).json()["data"]
        assert options
        assert all(option["reportKind"] == "base" for option in options)


async def test_answer_draft_rejects_invalid_payload_shapes(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr, "-shape")
        url = f"/api/v1/growth-tasks/{env['task']['id']}/answer-draft"
        bad_bodies = [
            {"text": "额外字段", "references": [], "expectedRevision": 0, "extra": 1},
            {"text": "布尔版本", "references": [], "expectedRevision": True},
            {"text": "浮点版本", "references": [], "expectedRevision": 0.0},
            {"text": "字符串版本", "references": [], "expectedRevision": "0"},
            {"text": "负版本", "references": [], "expectedRevision": -1},
            {"text": 123, "references": [], "expectedRevision": 0},
            {"text": None, "references": [], "expectedRevision": 0},
            {"text": "x" * 6001, "references": [], "expectedRevision": 0},
            {"text": "引用不是列表", "references": {}, "expectedRevision": 0},
            {"text": "缺引用字段", "expectedRevision": 0},
            {"text": "缺版本字段", "references": []},
            {
                "text": "引用缺字段",
                "references": [{"reportId": env["base"]["id"], "citationId": "X"}],
                "expectedRevision": 0,
            },
            {
                "text": "引用过长",
                "references": [
                    {
                        "reportId": env["base"]["id"],
                        "requirementId": env["task"]["requirementId"],
                        "citationId": "x" * 101,
                    }
                ],
                "expectedRevision": 0,
            },
            {
                "text": "引用为空",
                "references": [
                    {
                        "reportId": env["base"]["id"],
                        "requirementId": env["task"]["requirementId"],
                        "citationId": "",
                    }
                ],
                "expectedRevision": 0,
            },
            {
                # 客户端不得提交原文/评级/第三方标识，服务端从报告读取。
                "text": "客户端伪造原文",
                "references": [
                    {
                        "reportId": env["base"]["id"],
                        "requirementId": env["task"]["requirementId"],
                        "citationId": "R1-E1",
                        "snippet": "自带的原文",
                        "provenance": "reference",
                    }
                ],
                "expectedRevision": 0,
            },
        ]
        for body in bad_bodies:
            rejected = await student.put(url, json=body)
            assert rejected.status_code == 422, (body, rejected.text)
        boundary = await student.put(
            url, json={"text": "y" * 6000, "references": [], "expectedRevision": 0}
        )
        assert boundary.status_code == 200, boundary.text
        assert len(boundary.json()["data"]["text"]) == 6000


async def test_answer_draft_marks_references_unavailable_after_target_change(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr, "-drift")
        task, base = env["task"], env["base"]
        result, target = await complete_same_job_target(student, env)
        target_item = next(
            i for i in target["items"] if i["requirementId"] == task["requirementId"]
        )
        target_citation = next(
            e["citationId"] for e in target_item["evidenceList"] if e.get("citationId")
        )
        url = f"/api/v1/growth-tasks/{task['id']}/answer-draft"
        saved = await student.put(
            url,
            json={
                "text": "引用对照报告",
                "references": [
                    ref(base["id"], task["requirementId"], base_citation(env)),
                    ref(target["id"], task["requirementId"], target_citation),
                ],
                "expectedRevision": 0,
            },
        )
        assert saved.status_code == 200, saved.text

        # The only sanctioned rework path detaches the analysis by reselection;
        # the saved reference must stay readable but marked unavailable.
        async with factory() as session:
            row = await session.get(EvidenceGrowthTask, UUID(task["id"]))
            row.analysis_task_id = None
            row.status = "materials_selected"
            await session.commit()

        reread = (await student.get(url)).json()["data"]
        by_report = {r["reportId"]: r for r in reread["references"]}
        assert by_report[str(base["id"])]["available"] is True
        drifted = by_report[str(target["id"])]
        assert drifted["available"] is False
        assert drifted["snippet"] is None and drifted["provenance"] is None
        assert drifted["citationId"] == target_citation  # record kept, not deleted

        rejected = await student.put(
            url,
            json={
                "text": "重新验证",
                "references": [ref(target["id"], task["requirementId"], target_citation)],
                "expectedRevision": 1,
            },
        )
        assert rejected.status_code == 422, rejected.text
        still_there = (await student.get(url)).json()["data"]
        assert any(r["reportId"] == str(target["id"]) for r in still_there["references"])


async def test_answer_draft_treats_drifted_completed_target_as_unavailable(matching_db):  # noqa: F811
    """A completed target that no longer matches the task (jobId drift) must not
    back references: text is kept, its citations go unavailable, new saves are
    rejected and the selectable list never offers the mismatched report."""
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr, "-jobdrift")
        task, base = env["task"], env["base"]
        result, target = await complete_same_job_target(student, env)
        target_item = next(
            i for i in target["items"] if i["requirementId"] == task["requirementId"]
        )
        target_citation = next(
            e["citationId"] for e in target_item["evidenceList"] if e.get("citationId")
        )
        url = f"/api/v1/growth-tasks/{task['id']}/answer-draft"
        options_url = f"/api/v1/growth-tasks/{task['id']}/answer-draft/references"
        saved = await student.put(
            url,
            json={
                "text": "漂移前草稿",
                "references": [
                    ref(base["id"], task["requirementId"], base_citation(env)),
                    ref(target["id"], task["requirementId"], target_citation),
                ],
                "expectedRevision": 0,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["data"]["references"][1]["available"] is True

        # Post-completion jobId drift inside the disposable test DB: the analysis
        # input no longer points at the task's fixed target job.
        async with factory() as session:
            analysis = await session.get(AnalysisTask, UUID(result["analysisTaskId"]))
            analysis.input_snapshot = {
                **analysis.input_snapshot,
                "jobId": str(uuid4()),
            }
            await session.commit()

        # 草稿文本保留；目标引用降级为不可用；基准引用不受影响。
        reread = (await student.get(url)).json()["data"]
        assert reread["text"] == "漂移前草稿" and reread["revision"] == 1
        by_report = {r["reportId"]: r for r in reread["references"]}
        assert by_report[str(base["id"])]["available"] is True
        drifted = by_report[str(target["id"])]
        assert drifted["available"] is False
        assert drifted["snippet"] is None and drifted["provenance"] is None

        # 新PUT引用错配目标被拒绝；不含目标引用的保存仍可行。
        rejected = await student.put(
            url,
            json={
                "text": "重新引用错配目标",
                "references": [ref(target["id"], task["requirementId"], target_citation)],
                "expectedRevision": 1,
            },
        )
        assert rejected.status_code == 422, rejected.text
        current = (await student.get(url)).json()["data"]
        assert current["text"] == "漂移前草稿" and current["revision"] == 1
        ok = await student.put(url, json=draft_payload("仍可更新", revision=1))
        assert ok.status_code == 200, ok.text
        assert ok.json()["data"]["revision"] == 2

        # 可选列表不列错配目标，仅保留冻结基准条目。
        options = (await student.get(options_url)).json()["data"]
        assert options
        assert all(option["reportKind"] == "base" for option in options)


async def test_answer_draft_saves_leave_downstream_state_untouched(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        env = await setup_answer_env(student, hr, "-frozen")
        task, base = env["task"], env["base"]
        application = await student.post(
            "/api/v1/applications", json={"reportId": base["id"], "shareConsent": True}
        )
        assert application.status_code == 201, application.text
        app_id = application.json()["data"]["id"]
        assert (await hr.post(f"/api/v1/applications/{app_id}/view")).status_code == 200
        requirement_id = base["items"][0]["requirementId"]
        title = base["items"][0]["requirementTitle"]
        replied = await hr.post(
            f"/api/v1/applications/{app_id}/reply",
            json={
                "kind": "continue",
                "text": f"【第1项：{title}】\n请用新版材料说明运行结果（合成）。",
                "references": [{"requirementId": requirement_id, "citationIds": []}],
            },
        )
        assert replied.status_code == 200, replied.text

        # Baseline right before the first draft save; the drafts must change none of it.
        delivery_before = (await hr.post(f"/api/v1/applications/{app_id}/view")).json()["data"]
        reply_path = f"/api/v1/match-reports/{base['id']}/enterprise-replies/{requirement_id}"
        reply_before = (await student.get(reply_path)).json()["data"]
        notifications_before = {
            role: (await client.get("/api/v1/notifications")).json()["data"]
            for role, client in (("student", student), ("hr", hr))
        }
        task_before = (await student.get(f"/api/v1/growth-tasks/{task['id']}")).json()["data"]
        async with factory() as session:
            events_before = await session.scalar(select(func.count()).select_from(ApplicationEvent))
            usage_before = await session.scalar(select(func.count()).select_from(AiUsageLog))
            analyses_before = [
                (str(row.id), row.input_snapshot)
                for row in (await session.scalars(select(AnalysisTask))).all()
            ]
            task_row_before = (
                str(task["id"]),
                {
                    "status": task_before["status"],
                    "plan": task_before["plan"],
                    "materials": task_before["materials"],
                    "baseReportId": task_before["baseReportId"],
                    "analysisTaskId": task_before["analysisTaskId"],
                },
            )

        url = f"/api/v1/growth-tasks/{task['id']}/answer-draft"
        first = await student.put(url, json=draft_payload("草稿第一版", revision=0))
        assert first.status_code == 200, first.text
        second = await student.put(
            url,
            json={
                "text": "草稿第二版",
                "references": [ref(base["id"], requirement_id, base_citation(env))],
                "expectedRevision": 1,
            },
        )
        assert second.status_code == 200, second.text

        assert (await hr.post(f"/api/v1/applications/{app_id}/view")).json()[
            "data"
        ] == delivery_before
        assert (await student.get(reply_path)).json()["data"] == reply_before
        for role, client in (("student", student), ("hr", hr)):
            assert (await client.get("/api/v1/notifications")).json()[
                "data"
            ] == notifications_before[role]
        assert (await student.get(f"/api/v1/growth-tasks/{task['id']}")).json()[
            "data"
        ] == task_before
        async with factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(ApplicationEvent))
            ) == events_before
            assert (
                await session.scalar(select(func.count()).select_from(AiUsageLog))
            ) == usage_before
            analyses_after = [
                (str(row.id), row.input_snapshot)
                for row in (await session.scalars(select(AnalysisTask))).all()
            ]
            assert analyses_after == analyses_before
            row = await session.get(EvidenceGrowthTask, UUID(task["id"]))
            frozen = (
                row.status,
                row.plan,
                row.materials,
                str(row.base_report_id),
                str(row.analysis_task_id) if row.analysis_task_id else None,
            )
            assert frozen == (
                task_row_before[1]["status"],
                task_row_before[1]["plan"],
                task_row_before[1]["materials"],
                task_row_before[1]["baseReportId"],
                task_row_before[1]["analysisTaskId"],
            )
