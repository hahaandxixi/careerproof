"""Career changes distinguish source evidence from changing job criteria."""

import json
import logging
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.agents.provider import DeepSeekProvider
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.enums import TaskStatus
from app.schemas.analysis import (
    CareerPlanAnalysis,
    CareerPlanResult,
    JobRecommendationResult,
    RecommendationEvidence,
)
from app.services.career_planning import (
    CareerChangeAttributionConflict,
    CareerTaskEvidenceGapConflict,
    _source_key,
    compare_plans,
    validate_plan,
)
from app.tests.test_real_matching import (
    create_job,
    matching_db,  # noqa: F401
    register,
    upload_materials,
)

JOB = UUID("12345678-1234-4321-8765-abcdef123456")
OLD_VERSION = "11111111-1111-4111-8111-111111111111"
NEW_VERSION = "22222222-2222-4222-8222-222222222222"


def result(*, requirement="SQL 查询", weight=2, version=OLD_VERSION, priority="explore"):
    return JobRecommendationResult.model_validate({
        "summary": "合成规则候选",
        "materials": [{"kind": "resume", "id": version, "title": "合成简历", "versionNumber": 1,
                       "contentHash": "a" * 64}],
        "recommendations": [{
            "jobId": str(JOB), "jobTitle": "合成岗位", "companyName": "合成机构",
            "category": "data_analysis", "city": "深圳", "employmentType": "internship",
            "priority": priority, "assessedCount": 1, "requirementCount": 1,
            "supportedCount": 0, "claimedCount": 0,
            "requirements": [{"text": requirement, "skill": "SQL", "weight": weight,
                              "isRequired": True, "ruleVerdict": "gap"}],
        }],
    })


def test_job_requirement_change_cannot_be_attributed_to_new_material():
    change = compare_plans(
        result(), result(requirement="SQL 查询与运行记录", weight=4,
                         version=NEW_VERSION, priority="medium")
    )[0]
    assert change.materials_changed is True
    assert change.requirements_changed is True
    assert "岗位要求或权重已变化" in change.detail
    assert "不能把档位变化归因于补证" in change.detail


def test_rule_verdict_change_alone_is_not_a_job_requirement_edit():
    previous = result()
    current = result(version=NEW_VERSION)
    current.recommendations[0].requirements[0].rule_verdict = "supported"
    change = compare_plans(previous, current)[0]
    assert change.materials_changed is True
    assert change.requirements_changed is False


def test_reordering_identical_job_requirements_does_not_claim_the_job_changed():
    previous = result()
    second = previous.recommendations[0].requirements[0].model_copy(
        update={"text": "Python 脚本", "skill": "Python", "weight": 3}
    )
    previous.recommendations[0].requirements.append(second)
    current = previous.model_copy(deep=True)
    current.recommendations[0].requirements.reverse()
    change = compare_plans(previous, current)[0]
    assert change.requirements_changed is False
    assert "岗位要求或权重已变化" not in change.detail


def test_removing_one_of_two_identical_requirements_is_still_a_change():
    previous = result()
    previous.recommendations[0].requirements *= 2
    current = previous.model_copy(deep=True)
    current.recommendations[0].requirements.pop()
    assert compare_plans(previous, current)[0].requirements_changed is True


def test_same_job_metadata_edit_is_separate_from_requirements_and_materials():
    previous = result()
    current = previous.model_copy(deep=True)
    current.recommendations[0].job_title = "新版合成岗位"
    current.recommendations[0].city = "广州"
    change = compare_plans(previous, current)[0]
    assert change.job_details_changed is True
    assert change.requirements_changed is False
    assert change.materials_changed is False
    assert "岗位名称“合成岗位”→“新版合成岗位”" in change.detail
    assert "工作城市“深圳”→“广州”" in change.detail


def test_job_direction_and_employment_change_uses_readable_labels():
    previous = result()
    current = previous.model_copy(deep=True)
    current.recommendations[0].category = "software"
    current.recommendations[0].employment_type = "campus"
    change = compare_plans(previous, current)[0]
    assert change.job_details_changed is True
    assert change.requirements_changed is False
    assert "岗位方向“数据分析”→“软件开发”" in change.detail
    assert "用工类型“实习”→“校园招聘”" in change.detail


def test_material_version_and_job_details_both_appear_in_change_explanation():
    previous = result()
    current = result(version=NEW_VERSION, priority="medium")
    current.materials[0].version_number = 2
    current.recommendations[0].job_title = "新版合成岗位"
    change = compare_plans(previous, current)[0]
    assert change.materials_changed is True
    assert change.job_details_changed is True
    assert change.requirements_changed is False
    assert "所选材料版本已变化" in change.detail
    assert "上轮选用 简历“合成简历”第 1 版" in change.detail
    assert "本轮选用 简历“合成简历”第 2 版" in change.detail
    assert "岗位名称“合成岗位”→“新版合成岗位”" in change.detail
    assert "推荐档位 探索方向→值得比较" in change.detail
    assert "补证导致" not in change.detail


def test_previous_focus_job_missing_from_current_candidates_is_explained_without_cause():
    previous = result()
    current = result(version=NEW_VERSION)
    current.recommendations = []
    change = compare_plans(previous, current)[0]
    assert change.job_id == JOB
    assert change.status == "not_in_current"
    assert change.previous_priority == "explore"
    assert change.current_priority is None
    assert change.current_supported_count is None
    assert change.evidence_ids == []
    assert "未出现在本轮候选列表" in change.detail
    assert "不能判断岗位下架或本人能力变化" in change.detail


def test_old_job_still_in_full_current_candidates_is_not_marked_missing():
    previous = result()
    current = result(version=NEW_VERSION)
    old_job = current.recommendations[0]
    current.recommendations = [
        old_job.model_copy(update={"job_id": uuid4()}) for _ in range(3)
    ] + [old_job]
    changes = compare_plans(previous, current)
    assert all(change.status == "current" for change in changes)
    assert JOB not in {change.job_id for change in changes}


async def test_saved_plan_explains_closed_job_without_rewriting_first_snapshot(
    matching_db, monkeypatch,  # noqa: F811
):
    from app.services import career_planning

    def unavailable_provider():
        raise ValueError("synthetic provider outage")

    monkeypatch.setattr(career_planning, "get_ai_provider", unavailable_provider)
    app, factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(owner, "removed-job-owner@example.com")
        job = await create_job(owner)
        await register(student, "removed-job-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        payload = {
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            "externalAiConsent": True,
        }
        first_response = await student.post("/api/v1/career-plans", json=payload)
        assert first_response.status_code == 200, first_response.text
        first = first_response.json()["data"]
        assert [item["jobId"] for item in first["recommendations"]] == [job["id"]]

        closed = await owner.patch(f"/api/v1/jobs/{job['id']}", json={"status": "closed"})
        assert closed.status_code == 200, closed.text
        second_response = await student.post("/api/v1/career-plans", json=payload)
        assert second_response.status_code == 200, second_response.text
        second = second_response.json()["data"]
        assert second["previousPlanId"] == first["planId"]
        assert second["recommendations"] == []
        assert second["changes"] == [{
            "jobId": job["id"],
            "jobTitle": first["recommendations"][0]["jobTitle"],
            "status": "not_in_current",
            "previousSupportedCount": first["recommendations"][0]["supportedCount"],
            "currentSupportedCount": None,
            "previousPriority": first["recommendations"][0]["priority"],
            "currentPriority": None,
            "detail": second["changes"][0]["detail"],
            "materialsChanged": False,
            "requirementsChanged": False,
            "jobDetailsChanged": False,
            "evidenceIds": [],
        }]
        assert "不能判断岗位下架或本人能力变化" in second["changes"][0]["detail"]
        assert (await student.get("/api/v1/career-plans/latest")).json()["data"] == second
        async with factory() as session:
            original_task = await session.get(AnalysisTask, UUID(first["planId"]))
            assert original_task.input_snapshot["result"] == first


async def test_saved_plan_separates_job_details_edit_from_student_material_change(
    matching_db, monkeypatch,  # noqa: F811
):
    from app.services import career_planning

    def unavailable_provider():
        raise ValueError("synthetic provider outage")

    monkeypatch.setattr(career_planning, "get_ai_provider", unavailable_provider)
    app, factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(owner, "job-details-owner@example.com")
        job = await create_job(owner)
        await register(student, "job-details-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        payload = {
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            "externalAiConsent": True,
        }
        first_response = await student.post("/api/v1/career-plans", json=payload)
        assert first_response.status_code == 200, first_response.text
        first = first_response.json()["data"]
        old_title = first["recommendations"][0]["jobTitle"]
        old_city = first["recommendations"][0]["city"]

        edited = await owner.patch(f"/api/v1/jobs/{job['id']}", json={
            "title": "新版合成岗位", "city": "广州",
        })
        assert edited.status_code == 200, edited.text
        second_response = await student.post("/api/v1/career-plans", json=payload)
        assert second_response.status_code == 200, second_response.text
        second = second_response.json()["data"]
        assert second["previousPlanId"] == first["planId"]
        change = second["changes"][0]
        assert change["jobDetailsChanged"] is True
        assert change["requirementsChanged"] is False
        assert change["materialsChanged"] is False
        assert f"岗位名称“{old_title}”→“新版合成岗位”" in change["detail"]
        assert f"工作城市“{old_city}”→“广州”" in change["detail"]
        assert second["recommendations"][0]["jobTitle"] == "新版合成岗位"
        assert second["recommendations"][0]["city"] == "广州"
        async with factory() as session:
            original_task = await session.get(AnalysisTask, UUID(first["planId"]))
            assert original_task.input_snapshot["result"] == first


@pytest.mark.parametrize("model_claim,expected_status", [
    ("补证使推荐档位提升。", "change_attribution_conflict"),
    ("本轮只有材料变化，岗位没变。", "change_fact_conflict"),
])
async def test_saved_plan_explains_simultaneous_job_edit_and_project_version_change(
    model_claim, expected_status,
    matching_db, monkeypatch,  # noqa: F811
):
    from app.services import career_planning

    def unavailable_provider():
        raise ValueError("synthetic provider outage")

    monkeypatch.setattr(career_planning, "get_ai_provider", unavailable_provider)
    app, factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(owner, "mixed-change-owner@example.com")
        job = await create_job(owner)
        await register(student, "mixed-change-student@example.com", "student")
        resume, project, version = await upload_materials(student)
        payload = {
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            "externalAiConsent": True,
        }
        first_response = await student.post("/api/v1/career-plans", json=payload)
        assert first_response.status_code == 200, first_response.text
        first = first_response.json()["data"]

        edited = await owner.patch(f"/api/v1/jobs/{job['id']}", json={
            "title": "新版合成岗位", "city": "广州",
        })
        assert edited.status_code == 200, edited.text
        uploaded = await student.post(
            f"/api/v1/projects/{project['id']}/versions",
            data={"requestId": str(uuid4())},
            files={"file": (
                "new-version.txt", "新版材料展示了不同的项目内容。".encode(), "text/plain",
            )},
        )
        assert uploaded.status_code == 202, uploaded.text
        new_version = uploaded.json()["data"]
        task = await student.get(f"/api/v1/analysis-tasks/{new_version['taskId']}")
        assert task.status_code == 200, task.text
        assert task.json()["data"]["status"] == "completed"

        async def handler(request):
            planning_data = json.loads(json.loads(request.content)["messages"][1]["content"])
            sent_change = planning_data["changesFromPreviousPlan"][0]
            assert sent_change["materialsChanged"] is True
            assert sent_change["jobDetailsChanged"] is True
            assert sent_change["requirementsChanged"] is False
            assert "所选材料版本已变化" in sent_change["detail"]
            jobs = planning_data["jobs"]
            answer = {
                "comparison": model_claim,
                "focusJobId": jobs[0]["jobId"],
                "advice": [{
                    "jobId": job_input["jobId"],
                    "reason": "请核对当前项目材料。",
                    "keyGap": "运行记录待核验。",
                    "nextTask": "补充具名项目实现材料。",
                    "citationIds": [],
                } for job_input in jobs],
            }
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 60},
            })

        monkeypatch.setattr(career_planning, "get_ai_provider", lambda: DeepSeekProvider(
            api_key="synthetic-key", base_url="https://api.deepseek.com",
            model="deepseek-flash", timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        ))
        payload["projectVersionIds"] = [new_version["versionId"]]
        second_response = await student.post("/api/v1/career-plans", json=payload)
        assert second_response.status_code == 200, second_response.text
        second = second_response.json()["data"]
        assert second["previousPlanId"] == first["planId"]
        change = second["changes"][0]
        assert change["materialsChanged"] is True
        assert change["jobDetailsChanged"] is True
        assert change["requirementsChanged"] is False
        assert "所选材料版本已变化" in change["detail"]
        assert "上轮选用" in change["detail"]
        assert "本轮选用" in change["detail"]
        assert "岗位名称" in change["detail"]
        assert "工作城市" in change["detail"]
        assert "补证导致" not in change["detail"]
        assert second["aiStatus"] == expected_status
        assert second["aiPlan"] is None
        assert model_claim in second["aiValidationIssues"][0]["rejectedClaim"]
        assert (await student.get("/api/v1/career-plans/latest")).json()["data"] == second
        async with factory() as session:
            original_task = await session.get(AnalysisTask, UUID(first["planId"]))
            assert original_task.input_snapshot["result"] == first


async def test_career_api_does_not_call_reordered_requirements_a_job_edit(
    matching_db, monkeypatch,  # noqa: F811
):
    from app.services import career_planning

    def unavailable_provider():
        raise ValueError("synthetic provider outage")

    monkeypatch.setattr(career_planning, "get_ai_provider", unavailable_provider)
    app, _factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(owner, "reordered-job-owner@example.com")
        job = await create_job(owner, skills=("Python", "SQL"))
        await register(student, "reordered-job-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        payload = {
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            "externalAiConsent": True,
        }
        first_response = await student.post("/api/v1/career-plans", json=payload)
        assert first_response.status_code == 200, first_response.text
        old_requirements = job["requirements"]
        changed = await owner.patch(f"/api/v1/jobs/{job['id']}", json={
            "requirements": [
                {
                    "rawText": item["rawText"],
                    "skillName": item["skillName"],
                    "weight": item["weight"],
                    "isRequired": item["isRequired"],
                }
                for item in reversed(old_requirements)
            ],
        })
        assert changed.status_code == 200, changed.text
        second_response = await student.post("/api/v1/career-plans", json=payload)
        assert second_response.status_code == 200, second_response.text
        change = second_response.json()["data"]["changes"][0]
        assert change["requirementsChanged"] is False
        assert "岗位要求或权重已变化" not in change["detail"]


def test_non_version_directory_remains_part_of_source_identity():
    source = {"citationId": "J1-E1", "skill": "SQL", "filePath": "src/query.py",
              "lineStart": 1, "lineEnd": 2, "strength": "medium", "explanation": "合成代码",
              "snippet": "select 1"}
    first = RecommendationEvidence.model_validate(source)
    second = first.model_copy(update={"file_path": "tests/query.py"})
    assert _source_key(first) != _source_key(second)
    copied = first.model_copy(update={"file_path": f"{NEW_VERSION}/src/query.py"})
    assert _source_key(first) == _source_key(copied)


def plan():
    return CareerPlanAnalysis.model_validate({
        "comparison": "本轮材料与岗位要求均已变化，推荐档位需分别核对。",
        "focusJobId": str(JOB),
        "advice": [{
            "jobId": str(JOB), "reason": "当前材料尚未展示项目证据。",
            "keyGap": "运行记录仍需核对。", "nextTask": "上传可定位查询脚本。",
            "taskPlan": {"deliverable": "合成查询脚本", "steps": ["保存查询代码"],
                         "acceptanceChecks": ["脚本可定位"]},
            "citationIds": [],
        }],
    })


@pytest.mark.parametrize("field,claim", [
    ("comparison", "补证使推荐档位提升，说明职业方向更好。"),
    ("reason", "新版材料导致推荐优先级提高。"),
    ("next_task", "补证材料可让推荐顺序前移。"),
    ("step", "New evidence improved recommendation priority."),
    ("comparison", "因为补证，推荐档位提升。"),
    ("comparison", "补证后，推荐档位提高。"),
    ("reason", "推荐档位提高源于新版材料。"),
])
def test_ai_plan_rejects_unproven_recommendation_causality(field, claim):
    analysis = plan()
    if field == "comparison":
        analysis.comparison = claim
    elif field == "step":
        analysis.advice[0].task_plan.steps = [claim]
    else:
        setattr(analysis.advice[0], field, claim)
    with pytest.raises(CareerChangeAttributionConflict) as raised:
        validate_plan(analysis, result().recommendations)
    assert raised.value.claim == claim


def test_ai_plan_accepts_cooccurrence_without_causal_claim():
    analysis = plan()
    analysis.comparison = "新增证据与推荐档位变化同时出现，不能证明前者导致后者。"
    validate_plan(analysis, result().recommendations)


def test_ai_plan_preserves_explicit_denial_but_rejects_following_assertion():
    analysis = plan()
    analysis.comparison = "不能说补证使推荐档位提升；需分别核对岗位要求。"
    validate_plan(analysis, result().recommendations)
    analysis.comparison += "但补证使推荐档位提升。"
    with pytest.raises(CareerChangeAttributionConflict):
        validate_plan(analysis, result().recommendations)


@pytest.mark.parametrize("claim", [
    "本轮只有材料变化，岗位没变。",
    "材料版本未变，只是岗位名称改了。",
    "岗位要求保持不变，只有材料更新。",
])
def test_ai_plan_rejects_explicit_denial_of_structured_changes(claim):
    previous = result()
    current = result(version=NEW_VERSION)
    current.recommendations[0].job_title = "新版合成岗位"
    current.recommendations[0].requirements[0].text = "SQL 查询与运行记录"
    analysis = plan()
    analysis.comparison = claim
    with pytest.raises(ValueError, match="change fact"):
        validate_plan(analysis, current.recommendations, compare_plans(previous, current))


def test_ai_plan_allows_unchanged_requirements_when_only_job_details_and_materials_change():
    previous = result()
    current = result(version=NEW_VERSION)
    current.recommendations[0].job_title = "新版合成岗位"
    analysis = plan()
    analysis.comparison = "岗位要求未变，但所选材料版本和岗位名称均已变化；推荐档位仍需核对。"
    validate_plan(analysis, current.recommendations, compare_plans(previous, current))


def test_ai_plan_does_not_apply_one_jobs_detail_change_to_other_job_advice():
    previous = result()
    second_job_id = uuid4()
    second_job = previous.recommendations[0].model_copy(deep=True)
    second_job.job_id = second_job_id
    second_job.job_title = "另一合成岗位"
    previous.recommendations.append(second_job)
    current = previous.model_copy(deep=True)
    current.recommendations[0].job_title = "新版合成岗位"
    analysis = plan()
    second_advice = analysis.advice[0].model_copy(deep=True)
    second_advice.job_id = second_job_id
    second_advice.reason = "该岗位名称未变，当前材料仍需核对。"
    analysis.advice.append(second_advice)
    validate_plan(analysis, current.recommendations, compare_plans(previous, current))


def test_ai_plan_preserves_explicit_denial_of_unchanged_job_claim():
    previous = result()
    current = previous.model_copy(deep=True)
    current.recommendations[0].job_title = "新版合成岗位"
    changes = compare_plans(previous, current)
    analysis = plan()
    analysis.comparison = "不能说岗位未变；本轮岗位名称已变化。"
    validate_plan(analysis, current.recommendations, changes)
    analysis.comparison += "但岗位未变。"
    with pytest.raises(ValueError, match="change fact"):
        validate_plan(analysis, current.recommendations, changes)


@pytest.mark.parametrize("verdict", ["gap", "claimed_only"])
def test_career_task_without_project_implementation_evidence_needs_more_than_runtime_log(verdict):
    ranked = result()
    ranked.recommendations[0].requirements[0].rule_verdict = verdict
    analysis = plan()
    analysis.advice[0].task_plan.deliverable = "SQL 运行日志"
    analysis.advice[0].task_plan.steps = ["执行 SQL 查询并保存输出"]
    with pytest.raises(CareerTaskEvidenceGapConflict) as raised:
        validate_plan(analysis, ranked.recommendations)
    assert "SQL 运行日志" in raised.value.claim

    analysis.advice[0].task_plan.deliverable = "SQL 查询代码与运行记录"
    analysis.advice[0].task_plan.steps = ["提供可定位 SQL 查询代码", "执行查询并保存脱敏输出"]
    validate_plan(analysis, ranked.recommendations)


@pytest.mark.parametrize(
    "invalid_field", [
        "citation", "causality", "causality_after", "change_fact", "structure", "runtime_only",
    ]
)
async def test_saved_plan_rechecks_ai_before_display_without_changing_snapshot(
    matching_db, invalid_field,  # noqa: F811
):
    app, factory = matching_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student:
        user = await register(student, f"saved-plan-{invalid_field}@example.com", "student")
        saved = CareerPlanResult.model_validate({
            **result().model_dump(),
            "ai_plan": plan().model_dump(),
            "ai_status": "validated",
        })
        if invalid_field == "citation":
            saved.ai_plan.advice[0].citation_ids = ["unknown-source"]
        elif invalid_field == "causality":
            saved.ai_plan.comparison = "补证使推荐档位提升。"
        elif invalid_field == "causality_after":
            saved.ai_plan.comparison = "补证后，推荐档位提高。"
        elif invalid_field == "change_fact":
            current = result(version=NEW_VERSION)
            current.recommendations[0].job_title = "新版合成岗位"
            saved.materials = current.materials
            saved.recommendations = current.recommendations
            saved.changes = compare_plans(result(), current)
            saved.ai_plan.comparison = "本轮只有材料变化，岗位没变。"
        elif invalid_field == "runtime_only":
            saved.ai_plan.advice[0].task_plan.deliverable = "SQL 运行日志"
            saved.ai_plan.advice[0].task_plan.steps = ["执行 SQL 查询并保存输出"]
        async with factory() as session:
            task = AnalysisTask(
                created_by=UUID(user["id"]),
                task_type="career_plan",
                status=TaskStatus.COMPLETED,
                progress=100,
                input_snapshot={},
            )
            session.add(task)
            await session.flush()
            saved.plan_id = task.id
            original = saved.model_dump(mode="json", by_alias=True)
            if invalid_field == "structure":
                original["aiPlan"]["advice"] = []
            task.input_snapshot = {"version": "older-policy", "result": original}
            await session.commit()

        response = await student.get("/api/v1/career-plans/latest")
        assert response.status_code == 200, response.text
        shown = response.json()["data"]
        assert shown["planId"] == original["planId"]
        assert shown["recommendations"] == original["recommendations"]
        assert shown["aiPlan"] is None
        assert shown["aiStatus"] == "saved_plan_needs_recheck"
        assert shown["aiFallbackUsed"] is True
        if invalid_field == "change_fact":
            assert "变化说明与保存的材料或岗位变化冲突" in shown["aiValidationIssues"][0]["reason"]
            assert "岗位没变" in shown["aiValidationIssues"][0]["rejectedClaim"]
        async with factory() as session:
            persisted = await session.get(AnalysisTask, task.id)
            assert persisted.input_snapshot["result"] == original


async def test_api_saves_rejected_model_claim_and_rule_candidates(matching_db, monkeypatch):  # noqa: F811
    from app.services import career_planning

    async def handler(request):
        jobs = json.loads(json.loads(request.content)["messages"][1]["content"])["jobs"]
        answer = {
            "comparison": "补证使推荐档位提升。",
            "focusJobId": jobs[0]["jobId"],
            "advice": [{
                "jobId": job["jobId"], "reason": "当前材料需要继续核对。",
                "keyGap": "运行记录待核验。", "nextTask": "补充运行记录。",
                "taskPlan": {"deliverable": "运行记录", "steps": ["保存运行记录"],
                             "acceptanceChecks": ["记录可定位"]},
                "citationIds": [entry["citationId"] for entry in job["evidence"][:1]],
            } for job in jobs],
        }
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 90, "completion_tokens": 50},
        })

    monkeypatch.setattr(career_planning, "get_ai_provider", lambda: DeepSeekProvider(
        api_key="synthetic-key", base_url="https://api.deepseek.com",
        model="deepseek-flash", timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ))
    app, factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as hr,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(hr, "causal-hr@example.com")
        await create_job(hr)
        await register(student, "causal-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        response = await student.post("/api/v1/career-plans", json={
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            "externalAiConsent": True,
        })
        assert response.status_code == 200, response.text
        saved = response.json()["data"]
        assert saved["aiStatus"] == "change_attribution_conflict"
        assert saved["aiFallbackUsed"] is True
        assert saved["aiPlan"] is None
        assert saved["recommendations"]
        assert "补证使推荐档位提升" in saved["aiValidationIssues"][0]["rejectedClaim"]
        assert (await student.get("/api/v1/career-plans/latest")).json()["data"] == saved
        async with factory() as session:
            usage = list(await session.scalars(select(AiUsageLog)))
            assert len(usage) == 1
            assert usage[0].input_tokens == 90


async def test_api_keeps_rule_candidates_when_ai_task_only_asks_for_runtime(
    matching_db, monkeypatch,  # noqa: F811
):
    from app.services import career_planning

    async def handler(request):
        jobs = json.loads(json.loads(request.content)["messages"][1]["content"])["jobs"]
        assert len(jobs) == 1
        assert any(
            requirement["skill"] == "SQL"
            and requirement["ruleVerdict"] in {"gap", "claimed_only"}
            for requirement in jobs[0]["requirements"]
        )
        answer = {
            "comparison": "当前 SQL 实现证据需要补充。",
            "focusJobId": jobs[0]["jobId"],
            "advice": [{
                "jobId": jobs[0]["jobId"],
                "reason": "当前材料未展示 SQL 实现。",
                "keyGap": "缺少可定位的查询代码。",
                "nextTask": "补充 SQL 查询实现与运行记录。",
                "taskPlan": {
                    "deliverable": "SQL 运行日志",
                    "steps": ["执行 SQL 查询并保存输出"],
                    "acceptanceChecks": ["记录可定位"],
                },
                "citationIds": [],
            }],
        }
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 90, "completion_tokens": 50},
        })

    monkeypatch.setattr(career_planning, "get_ai_provider", lambda: DeepSeekProvider(
        api_key="synthetic-key", base_url="https://api.deepseek.com",
        model="deepseek-flash", timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ))
    app, _factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as hr,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(hr, "runtime-only-hr@example.com")
        await create_job(hr, skills=("SQL",))
        await register(student, "runtime-only-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        response = await student.post("/api/v1/career-plans", json={
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            "externalAiConsent": True,
        })
        assert response.status_code == 200, response.text
        saved = response.json()["data"]
        assert saved["aiStatus"] == "task_plan_evidence_gap_conflict"
        assert saved["aiFallbackUsed"] is True
        assert saved["aiPlan"] is None
        assert saved["recommendations"]
        assert "SQL 运行日志" in saved["aiValidationIssues"][0]["rejectedClaim"]
        assert (await student.get("/api/v1/career-plans/latest")).json()["data"] == saved


async def test_ai_budget_database_fault_surfaces_instead_of_faking_rule_fallback(
    matching_db, monkeypatch, caplog  # noqa: F811
):
    """B-10: a real database fault inside the AI stage must surface, not fake success."""
    from app.services import career_planning

    budget_entries = []
    failing_statement = "SELECT * FROM cp_missing_budget_fault_probe"

    async def broken_budget(session, _user_id):
        # Use a failing SQL statement instead of dropping the fixture's table:
        # PostgreSQL's search_path can fall back to a public table of that name.
        budget_entries.append(True)
        await session.execute(text(failing_statement))
        raise AssertionError("unreachable")

    monkeypatch.setattr(career_planning, "_daily_ai_budget", broken_budget)
    app, _factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(owner, "db-fault-owner@example.com")
        await create_job(owner)
        await register(student, "db-fault-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        payload = {
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            "externalAiConsent": True,
        }
        with (
            caplog.at_level(logging.WARNING, logger="app.services.career_planning"),
            pytest.raises(SQLAlchemyError) as fault,
        ):
            await student.post("/api/v1/career-plans", json=payload)
        assert budget_entries == [True], "the injected AI budget check must be reached exactly once"
        assert fault.value.statement == failing_statement
        records = [
            record for record in caplog.records
            if record.name == "app.services.career_planning"
        ]
        assert len(records) == 1
        assert records[0].getMessage() == "career_plan.ai_stage_database_fault"
        assert records[0].db_error == type(fault.value).__name__
        assert records[0].stage == "ai_budget_check"
        flat = f"{records[0].getMessage()} {records[0].db_error} {records[0].stage}"
        assert "本人完成Python课程项目" not in flat
        assert "synthetic provider outage" not in flat
        assert "synthetic-key" not in flat
        assert "ai_usage_logs" not in flat


async def test_model_stage_failure_still_degrades_to_rule_candidates(
    matching_db, monkeypatch  # noqa: F811
):
    """B-10 regression: bounded model failures keep the designed rule fallback."""
    from app.services import career_planning

    def unavailable_provider():
        raise ValueError("synthetic provider outage")

    monkeypatch.setattr(career_planning, "get_ai_provider", unavailable_provider)
    app, _factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(owner, "degrade-owner@example.com")
        job = await create_job(owner)
        await register(student, "degrade-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        response = await student.post("/api/v1/career-plans", json={
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            "externalAiConsent": True,
        })
        assert response.status_code == 200, response.text
        saved = response.json()["data"]
        assert saved["aiStatus"] == "model_unavailable_or_invalid"
        assert saved["aiFallbackUsed"] is True
        assert saved["aiPlan"] is None
        assert [item["jobId"] for item in saved["recommendations"]] == [job["id"]]
        latest = await student.get("/api/v1/career-plans/latest")
        assert latest.json()["data"]["planId"] == saved["planId"]
