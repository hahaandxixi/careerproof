from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import AppError
from app.models.analysis import AnalysisTask, MatchReport
from app.schemas.analysis import CareerTaskPlan, CodeEvidenceView, ReportMaterial
from app.services.report_comparison import compare_views, evidence_key
from app.tests.test_jobs_api import job_payload, jobs_db, organization, register  # noqa: F401


def evidence(**patch):
    return CodeEvidenceView.model_validate({
        "citation_id": "R1-E1", "skill": "Python", "evidence_type": "python_code",
        "file_path": f"{uuid4()}/app.py", "line_start": 1, "line_end": 2,
        "snippet": "return 1", "strength": "medium", "explanation": "合成证据",
        "content_hash": "hash", **patch,
    })


def pair():
    requirement_id = uuid4()
    def item():
        return NS(requirement_id=requirement_id, requirement_title="Python实践",
                  evidence_list=[evidence()], formula_version="v1", evidence_level_version="l1",
                  confirmation_status=None, reviewer_note=None,
                  ai_status="validated", evidence_level=2)
    shared = dict(job_id=uuid4(), candidate_id="student", materials=[],
                  evidence_context_version="c1", ai_model="model", analysis_mode="ai_evidence",
                  ai_fallback_used=False)
    return NS(id=uuid4(), items=[item()], **shared), NS(id=uuid4(), items=[item()], **shared)


def test_citation_reordering_and_version_uuid_do_not_create_new_evidence():
    base, target = pair()
    target.items[0].evidence_list[0].citation_id = "R1-E3"
    diff = compare_views(base, target, {}, {})
    assert diff.items[0].changes == []
    assert evidence_key(base.items[0].evidence_list[0]) == evidence_key(
        target.items[0].evidence_list[0])


@pytest.mark.parametrize("old,new", [(1, 3), (3, 1), (None, 2), (2, None)])
def test_level_changes_include_unrated(old, new):
    base, target = pair()
    base.items[0].evidence_level = old
    target.items[0].evidence_level = new
    result = compare_views(base, target, {}, {}).items[0]
    assert result.base_level == old and result.target_level == new
    assert "level" in result.changes


def test_same_file_hash_different_snippet_is_not_silently_aligned():
    base, target = pair()
    target.items[0].evidence_list[0].snippet = "return 2"
    result = compare_views(base, target, {}, {}).items[0]
    assert len(result.added_evidence) == len(result.removed_evidence) == 1


@pytest.mark.parametrize("cause", ["materials", "requirements", "rule_version", "mixed"])
def test_context_changes_are_independent_or_combined(cause):
    base, target = pair()
    old, new = {}, {}
    if cause in {"materials", "mixed"}:
        target.materials = [ReportMaterial(kind="resume", id=uuid4(), title="合成简历",
                                           version_number=2, content_hash="new")]
    if cause in {"requirements", "mixed"}:
        new = {"requirements": [{"id": str(target.items[0].requirement_id), "weight": 5}]}
    if cause in {"rule_version", "mixed"}:
        target.items[0].formula_version = "v2"
    result = compare_views(base, target, old, new)
    assert set(result.context_changes) == (
        {"materials", "requirements", "rule_version"} if cause == "mixed" else {cause})


def test_added_and_removed_requirements_remain_visible():
    base, target = pair()
    target.items[0].requirement_id = uuid4()
    result = compare_views(base, target, {}, {})
    assert {item.status for item in result.items} == {"added", "removed"}


def test_cross_job_or_candidate_rejected():
    base, target = pair()
    target.job_id = uuid4()
    with pytest.raises(AppError):
        compare_views(base, target, {}, {})
    target.job_id = base.job_id
    target.candidate_id = "another"
    with pytest.raises(AppError):
        compare_views(base, target, {}, {})


def test_changed_explanation_and_gap_are_preserved_without_inventing_evidence():
    base, target = pair()
    base.items[0].ai_explanation = "可见源码，但未运行"
    base.items[0].ai_information_gap = "缺少运行记录"
    target.items[0].ai_explanation = "相同源码，另需核对实际输入输出"
    target.items[0].ai_information_gap = "结果记录未展示"
    result = compare_views(base, target, {}, {}).items[0]
    assert result.base_explanation == "可见源码，但未运行"
    assert result.target_information_gap == "结果记录未展示"
    assert result.changes == ["interpretation"]
    assert result.added_evidence == result.removed_evidence == []


def test_changed_advice_is_distinct_from_new_evidence_or_level_change():
    base, target = pair()
    base.items[0].ai_suggestion = "补充运行输出"
    target.items[0].ai_suggestion = "核对异常输入并保存响应"
    result = compare_views(base, target, {}, {}).items[0]
    assert result.changes == ["advice"]
    assert result.base_suggestion == "补充运行输出"
    assert result.target_suggestion == "核对异常输入并保存响应"
    assert result.added_evidence == result.removed_evidence == []
    assert result.base_level == result.target_level


def test_structured_plan_change_is_visible_when_suggestion_stays_the_same():
    base, target = pair()
    for item in (base.items[0], target.items[0]):
        item.ai_suggestion = "补充运行记录"
    target.items[0].ai_task_plan = CareerTaskPlan(
        deliverable="具名请求与响应", steps=["保存异常请求样例"],
        acceptance_checks=["输入和输出可定位"],
    )
    result = compare_views(base, target, {}, {}).items[0]
    assert result.changes == ["advice"]
    assert result.base_task_plan is None
    assert result.target_task_plan == target.items[0].ai_task_plan
    assert result.added_evidence == result.removed_evidence == []


@pytest.mark.parametrize("reason", ["failed", "redundant", "rejected", "corrected"])
def test_unusable_advice_and_plan_are_not_reintroduced_by_comparison(reason):
    base, target = pair()
    for item in (base.items[0], target.items[0]):
        item.ai_suggestion = "补充运行记录"
        item.ai_task_plan = CareerTaskPlan(
            deliverable="运行记录", steps=["记录请求"], acceptance_checks=["输出可定位"],
        )
    if reason == "failed":
        target.items[0].ai_status = "invalid_output"
    elif reason == "redundant":
        target.items[0].ai_suggestion_redundant = True
    else:
        target.items[0].confirmation_status = reason
    result = compare_views(base, target, {}, {}).items[0]
    assert result.base_suggestion and result.base_task_plan
    assert result.target_suggestion is None and result.target_task_plan is None
    assert "advice" in result.changes


@pytest.mark.parametrize("side", ["base", "target"])
def test_old_snapshot_repeated_source_advice_is_rechecked_without_mutation(side):
    base, target = pair()
    old = (base if side == "base" else target).items[0]
    old.evidence_list = [evidence(
        snippet="def total(values):\n    return sum(values)", context_complete=True,
        function_line_start=1, function_line_end=2,
    )]
    old.ai_suggestion = "请再次提交该函数源码。"
    old.ai_suggestion_redundant = False
    old.ai_task_plan = CareerTaskPlan(
        deliverable="函数源码", steps=["再次提交源码"], acceptance_checks=["代码可定位"],
    )
    result = compare_views(base, target, {}, {}).items[0]
    assert getattr(result, f"{side}_suggestion") is None
    assert getattr(result, f"{side}_task_plan") is None
    assert old.ai_suggestion == "请再次提交该函数源码。"
    assert old.ai_task_plan.deliverable == "函数源码"
    assert old.ai_suggestion_redundant is False


def test_saved_task_plan_warning_hides_only_the_unsafe_plan():
    base, target = pair()
    old = base.items[0]
    old.ai_suggestion = "补充运行记录"
    old.ai_task_plan = CareerTaskPlan(
        deliverable="具名运行记录", steps=["再次提交该函数源码"],
        acceptance_checks=["输出可定位"],
    )
    old.ai_task_plan_warning = "AI任务草稿重复要求提交已完整展示的源码，请重新核对。"
    result = compare_views(base, target, {}, {}).items[0]
    assert result.base_suggestion == old.ai_suggestion
    assert result.base_task_plan is None
    assert result.base_task_plan_warning == old.ai_task_plan_warning


def test_legacy_snapshot_without_warning_rechecks_task_plan_in_comparison():
    base, target = pair()
    old = base.items[0]
    old.evidence_list = [evidence(
        snippet="def total(values):\n    return sum(values)", context_complete=True,
        function_line_start=1, function_line_end=2,
    )]
    old.ai_suggestion = "补充运行记录"
    old.ai_task_plan = CareerTaskPlan(
        deliverable="具名运行记录", steps=["再次提交该函数源码"],
        acceptance_checks=["输出可定位"],
    )
    result = compare_views(base, target, {}, {}).items[0]
    assert result.base_suggestion == "补充运行记录"
    assert result.base_task_plan is None
    assert result.base_task_plan_warning == (
        "AI任务草稿重复要求提交已完整展示的源码，请重新核对。"
    )


async def test_comparison_http_permissions_and_previous_selection(jobs_db):  # noqa: F811
    app, factory = jobs_db
    transport = ASGITransport(app=app)
    async with (AsyncClient(transport=transport, base_url="http://test") as owner,
                AsyncClient(transport=transport, base_url="http://test") as student,
                AsyncClient(transport=transport, base_url="http://test") as outsider):
        await register(owner, "compare-hr@example.com")
        org = await organization(owner)
        job = (await owner.post("/api/v1/jobs", json=job_payload(org))).json()["data"]
        candidate = await register(student, "compare-student@example.com", "student")
        other = await register(outsider, "compare-other@example.com", "student")
        ids = []
        async with factory() as session:
            for offset in (0, 1):
                task = AnalysisTask(created_by=UUID(candidate["id"]), task_type="job_match")
                session.add(task)
                await session.flush()
                report = MatchReport(analysis_task_id=task.id, job_id=UUID(job["id"]),
                                     candidate_ref=candidate["id"], summary="合成报告",
                                     created_at=datetime.now(UTC) + timedelta(seconds=offset))
                session.add(report)
                await session.flush()
                ids.append(report.id)
            hidden_task = AnalysisTask(created_by=UUID(other["id"]), task_type="job_match")
            session.add(hidden_task)
            await session.flush()
            hidden = MatchReport(analysis_task_id=hidden_task.id, job_id=UUID(job["id"]),
                                 candidate_ref=other["id"], summary="其他学生报告")
            session.add(hidden)
            await session.flush()
            hidden_id = hidden.id
            await session.commit()
        url = f"/api/v1/match-reports/{ids[0]}/comparison/{ids[1]}"
        response = await student.get(url)
        assert response.status_code == 200, response.text
        assert (await outsider.get(url)).status_code == 404
        assert (await owner.get(url)).status_code == 404
        for base_id, target_id in ((ids[0], hidden_id), (hidden_id, ids[1])):
            denied = await student.get(
                f"/api/v1/match-reports/{base_id}/comparison/{target_id}")
            assert denied.status_code == 404
        assert (await student.get(
            f"/api/v1/match-reports/{ids[0]}/previous-comparison"
        )).json()["data"] is None
        previous = await student.get(f"/api/v1/match-reports/{ids[1]}/previous-comparison")
        assert previous.status_code == 200, previous.text
        assert previous.json()["data"]["baseId"] == str(ids[0])
        assert (await student.get(
            f"/api/v1/match-reports/{ids[0]}/comparison/{ids[0]}"
        )).status_code == 409
