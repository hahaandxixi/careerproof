"""Enterprise verification uses only synthetic snapshots and isolated model HTTP."""

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.agents.provider import DeepSeekProvider
from app.core.config import settings
from app.models.analysis import AgentStep, AiUsageLog, AnalysisTask, MatchItem, MatchReport
from app.models.enums import MembershipRole, TaskStatus
from app.models.identity import EnterpriseMembership, StudentProfile, User
from app.models.recruitment import Application, JobRequirement
from app.services import application_verification as verification
from app.services.task_runner import FastAPIBackgroundTaskRunner
from app.tests.test_applications_api import close, setup
from app.tests.test_jobs_api import register
from app.tests.test_real_matching import matching_db  # noqa: F401

SYNTHETIC_KEY = "sk-synthetic-verification-key-000001"


def citation(identifier, snippet, *, provenance="portfolio", path="analysis.py"):
    return {
        "citationId": identifier,
        "provenance": provenance,
        "contextComplete": True,
        "contextNote": "完整合成片段",
        "skill": "Excel",
        "evidenceType": "implementation",
        "filePath": path,
        "lineStart": 1,
        "lineEnd": len(snippet.splitlines()),
        "snippet": snippet,
        "strength": "strong",
        "explanation": "合成原文",
        "contentHash": "a" * 64,
    }


def model_answer(snapshot):
    first, missing, contradiction = snapshot["items"]
    return {
        "items": [
            {
                "requirementId": first["requirementId"],
                "visibleSupport": "片段显示对数据列求和的实现。",
                "informationGap": "尚未提供实际运行记录和本人贡献说明。",
                "verificationQuestions": ["请演示样例输入输出，并说明本人负责的部分。"],
                "nextStep": None,
                "nextStepReason": None,
                "citationIds": ["R1-E1"],
            },
            {
                "requirementId": missing["requirementId"],
                "visibleSupport": None,
                "informationGap": "本次授权材料没有展示 SQL 查询实现。",
                "verificationQuestions": ["请补充一条查询和对应结果。"],
                "nextStep": None,
                "nextStepReason": None,
                "citationIds": [],
            },
            {
                "requirementId": contradiction["requirementId"],
                "visibleSupport": "文档声明任务已完成，代码片段却仍抛出未实现异常。",
                "informationGap": "文档与代码不一致，真实实现及运行状态待核验。",
                "verificationQuestions": ["请说明文档与代码差异，并提供实际可运行版本。"],
                "nextStep": None,
                "nextStepReason": None,
                "citationIds": ["R3-E1", "R3-E2"],
            },
        ]
    }


def completion(answer, *, finish_reason="stop"):
    return httpx.Response(
        200,
        json={
            "model": "deepseek-flash",
            "choices": [{
                "message": {"content": answer if isinstance(answer, str) else json.dumps(
                    answer, ensure_ascii=False
                )},
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": 123,
                "completion_tokens": 45,
                "prompt_tokens_details": {"cached_tokens": 17},
            },
        },
    )


def inject_provider(monkeypatch, handler, *, max_attempts=1):
    provider = DeepSeekProvider(
        api_key=SYNTHETIC_KEY,
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=max_attempts,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(verification, "get_ai_provider", lambda: provider)
    return provider


@dataclass
class Case:
    hr: AsyncClient
    student: AsyncClient
    outsider: AsyncClient
    application_id: str
    report_id: UUID
    job: dict
    snapshot: dict
    factory: object
    app: object
    submitted: list

    @property
    def path(self):
        return f"/api/v1/applications/{self.application_id}/verification"

    async def start(self, client=None):
        response = await (client or self.hr).post(
            self.path, json={"externalAiConsent": True}
        )
        assert response.status_code == 202, response.text
        return response.json()["data"]

    async def execute(self, started):
        await verification.execute_application_verification_task(
            UUID(started["taskId"]), session_factory=self.factory
        )

    async def result(self, started, client=None):
        response = await (client or self.hr).get(f"{self.path}/{started['taskId']}")
        assert response.status_code == 200, response.text
        return response.json()["data"]


@pytest.fixture
async def case(matching_db, tmp_path, monkeypatch):  # noqa: F811
    hr, student, outsider, job, report_id, _resume_id, _raw, factory = await setup(
        matching_db, tmp_path, monkeypatch
    )
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", 40_000)
    submitted = []

    def capture(_runner, _background, callback, *args):
        submitted.append((callback, args))

    monkeypatch.setattr(FastAPIBackgroundTaskRunner, "submit", capture)

    async def forbidden_network(request):
        pytest.fail(f"Unconfigured synthetic model request: {request.url}")

    inject_provider(monkeypatch, forbidden_network)
    async with factory() as session:
        item = await session.scalar(select(MatchItem).where(MatchItem.report_id == report_id))
        item.verdict = "supported"
        first = citation("R1-E1", "def total(values):\n    return sum(values)\n")
        item.evidence_snapshot = {
            **item.evidence_snapshot,
            "evidence": first,
            "evidenceList": [first],
        }
        for skill, text, verdict, evidence in (
            ("SQL", "能够编写SQL查询", "gap", []),
            ("Python", "能够实现数据导出", "partial", [
                citation("R3-E1", "导出功能已全部完成。", path="README.md"),
                citation("R3-E2", "def export():\n    raise NotImplementedError\n"),
            ]),
        ):
            requirement = JobRequirement(
                job_id=UUID(job["id"]), skill_name=skill, raw_text=text
            )
            session.add(requirement)
            await session.flush()
            session.add(MatchItem(
                report_id=report_id,
                requirement_id=requirement.id,
                rule_base_score=0.5 if evidence else 0,
                weight=1,
                final_score=50 if evidence else 0,
                verdict=verdict,
                explanation="独立合成要求",
                formula_version="synthetic",
                evidence_snapshot={
                    "skill": skill,
                    "requirementTitle": text,
                    "claimed": bool(evidence),
                    "evidence": evidence[0] if evidence else None,
                    "evidenceList": evidence,
                },
            ))
        await session.commit()
    response = await student.post(
        "/api/v1/applications", json={"reportId": str(report_id), "shareConsent": True}
    )
    assert response.status_code == 201, response.text
    application_id = response.json()["data"]["id"]
    opened = await hr.post(f"/api/v1/applications/{application_id}/view")
    assert opened.status_code == 200, opened.text
    snapshot = opened.json()["data"]["report"]
    # Database ordering is not a model contract: order the synthetic fixtures by skill.
    snapshot["items"].sort(key=lambda value: {"Excel": 0, "SQL": 1, "Python": 2}[value["skill"]])
    async with factory() as session:
        application = await session.get(Application, UUID(application_id))
        application.report_snapshot = deepcopy(snapshot)
        await session.commit()
    try:
        yield Case(
            hr, student, outsider, application_id, report_id, job,
            snapshot, factory, matching_db[0], submitted
        )
    finally:
        await close(hr, student, outsider)


async def test_consent_enterprise_scope_and_authorized_snapshot_required(case):
    assert (await case.hr.post(case.path, json={})).status_code == 422
    assert (await case.hr.post(
        case.path, json={"externalAiConsent": False}
    )).status_code == 422
    for client in (case.student, case.outsider):
        assert (await client.post(
            case.path, json={"externalAiConsent": True}
        )).status_code == 404
        assert (await client.get(case.path)).status_code == 404
    assert (await case.hr.get(case.path)).json()["data"] is None
    async with case.factory() as session:
        application = await session.get(Application, UUID(case.application_id))
        application.consent_at = None
        await session.commit()
    assert (await case.hr.post(
        case.path, json={"externalAiConsent": True}
    )).status_code == 404
    assert not case.submitted


async def test_structured_support_gap_contradiction_and_completed_cache(case, monkeypatch):
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["response_format"] == {"type": "json_object"}
        assert 0 < body["max_tokens"] <= settings.ai_per_report_output_token_limit
        assert request.headers["authorization"] == f"Bearer {SYNTHETIC_KEY}"
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    assert started["status"] == "pending" and started["analysis"] is None
    pending = await case.start()
    assert pending["taskId"] == started["taskId"] and pending["reused"] is True
    await case.execute(started)
    result = await case.result(started)
    assert result["status"] == "completed" and result["aiStatus"] == "validated"
    assert result["analysis"]["items"] == model_answer(case.snapshot)["items"]
    assert result["usage"]["inputTokens"] == 123
    assert result["usage"]["outputTokens"] == 45
    assert result["usage"]["cacheHitTokens"] == 17
    assert result["dailyBudget"]["knownInputTokens"] == 123
    assert result["dailyBudget"]["knownOutputTokens"] == 45
    assert result["dailyBudget"]["heldInputBound"] == 0
    assert result["dailyBudget"]["unknownReservationCount"] == 0
    assert result["inputPreflights"][0]["allowed"] is True
    assert len(result["snapshotHash"]) == 64
    assert result["promptVersion"]
    reused = await case.start()
    assert reused["taskId"] == started["taskId"] and reused["reused"] is True
    assert len(requests) == 1
    assert reused["dailyBudget"] == result["dailyBudget"]
    assert (await case.hr.get(case.path)).json()["data"]["taskId"] == started["taskId"]
    current = (await case.hr.post(
        f"/api/v1/applications/{case.application_id}/view"
    )).json()["data"]["report"]
    assert current == case.snapshot
    async with case.factory() as session:
        report = await session.get(MatchReport, case.report_id)
        assert report.summary == "合成证据报告" and report.overall_score == 50
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.task_type == "application_verification"
        usage = await session.scalar(select(AiUsageLog).where(
            AiUsageLog.analysis_task_id == task.id
        ))
        assert usage.input_tokens == 123 and usage.cache_hit_tokens == 17


@pytest.mark.parametrize("corruption", ["cross_requirement", "hiring_decision"])
async def test_saved_advice_is_revalidated_on_read_and_not_reused(case, monkeypatch, corruption):
    async def handler(_request):
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    await case.execute(started)
    assert (await case.result(started))["aiStatus"] == "validated"

    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        saved = deepcopy(task.input_snapshot)
        if corruption == "cross_requirement":
            saved["analysis"]["items"][0]["citationIds"] = ["R3-E1"]
        else:
            saved["analysis"]["items"][0]["verificationQuestions"] = ["建议录用该候选人"]
        task.input_snapshot = saved
        await session.commit()

    for path in (case.path, f"{case.path}/{started['taskId']}"):
        response = await case.hr.get(path)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert data["aiStatus"] == "invalidated"
        assert data["failureKind"] == "saved_validation_failed"
        assert data["analysis"] is None

    replacement = await case.start()
    assert replacement["taskId"] != started["taskId"]
    assert replacement["status"] == "pending" and replacement["reused"] is False
    async with case.factory() as session:
        original = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert original.input_snapshot == saved
        application = await session.get(Application, UUID(case.application_id))
        assert application.report_snapshot == case.snapshot


@pytest.mark.parametrize("invalid", ["unknown", "cross_requirement"])
async def test_invalid_citations_fail_without_overwriting_report(case, monkeypatch, invalid):
    answer = model_answer(case.snapshot)
    answer["items"][0]["citationIds"] = [
        "R999-E999" if invalid == "unknown" else "R3-E1"
    ]
    calls = []

    async def handler(request):
        calls.append(request)
        return completion(answer)

    inject_provider(monkeypatch, handler)
    started = await case.start()
    await case.execute(started)
    result = await case.result(started)
    assert result["status"] == "failed" and result["analysis"] is None
    assert result["failureKind"] and result["usage"]["inputTokens"] == 123
    assert len(calls) == 1
    snapshot = (await case.hr.post(
        f"/api/v1/applications/{case.application_id}/view"
    )).json()["data"]["report"]
    assert snapshot == case.snapshot


async def test_live_report_edits_cannot_change_verification_input(case, monkeypatch):
    async with case.factory() as session:
        report = await session.get(MatchReport, case.report_id)
        report.summary = "后续私有修改不应外发"
        item = await session.scalar(select(MatchItem).where(MatchItem.report_id == report.id))
        item.evidence_snapshot = {**item.evidence_snapshot, "claimText": "私有新增内容"}
        await session.commit()

    async def handler(request):
        text = request.content.decode()
        assert "后续私有修改不应外发" not in text and "私有新增内容" not in text
        assert "return sum(values)" in text
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    await case.execute(started)
    assert (await case.result(started))["status"] == "completed"


async def test_snapshot_change_invalidates_old_result_and_cache(case, monkeypatch):
    inject_provider(monkeypatch, lambda request: completion(model_answer(case.snapshot)))
    first = await case.start()
    await case.execute(first)
    changed = deepcopy(case.snapshot)
    changed["items"][0]["explanation"] = "快照内容改变必须重新授权核验结果口径"
    async with case.factory() as session:
        application = await session.get(Application, UUID(case.application_id))
        application.report_snapshot = changed
        await session.commit()
    assert (await case.hr.get(f"{case.path}/{first['taskId']}")).status_code == 409
    assert (await case.hr.get(case.path)).json()["data"] is None
    second = await case.start()
    assert second["taskId"] != first["taskId"]
    assert second["snapshotHash"] != first["snapshotHash"] and not second["reused"]


async def test_withdrawal_before_worker_blocks_model_and_all_result_paths(case, monkeypatch):
    requests = []

    async def handler(request):
        requests.append(request)
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    withdrawn = await case.student.post(
        f"/api/v1/applications/{case.application_id}/withdraw"
    )
    assert withdrawn.status_code == 200
    await case.execute(started)
    assert not requests
    for path in (
        case.path,
        f"{case.path}/{started['taskId']}",
        f"/api/v1/analysis-tasks/{started['taskId']}",
        f"/api/v1/analysis-tasks/{started['taskId']}/events",
    ):
        response = await case.hr.get(path)
        assert response.status_code == 404, response.text
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.CANCELLED


async def test_withdrawal_while_provider_returns_discards_analysis_but_keeps_usage(
    case, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()

    async def handler(request):
        entered.set()
        await release.wait()
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    work = asyncio.create_task(case.execute(started))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert (await case.student.post(
            f"/api/v1/applications/{case.application_id}/withdraw"
        )).status_code == 200
    finally:
        release.set()
        await asyncio.wait_for(work, 5)
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.CANCELLED
        assert task.input_snapshot.get("analysis") is None
        usage = await session.scalar(select(AiUsageLog).where(
            AiUsageLog.analysis_task_id == task.id
        ))
        assert usage is not None and usage.input_tokens == 123
    assert (await case.hr.get(f"{case.path}/{started['taskId']}")).status_code == 404


async def test_completed_result_is_revoked_in_specific_generic_and_sse_paths(case, monkeypatch):
    inject_provider(monkeypatch, lambda request: completion(model_answer(case.snapshot)))
    started = await case.start()
    await case.execute(started)
    assert (await case.result(started))["analysis"]
    await case.student.post(f"/api/v1/applications/{case.application_id}/withdraw")
    for path in (
        case.path,
        f"{case.path}/{started['taskId']}",
        f"/api/v1/analysis-tasks/{started['taskId']}",
        f"/api/v1/analysis-tasks/{started['taskId']}/events",
    ):
        assert (await case.hr.get(path)).status_code == 404
    assert (await case.hr.post(case.path, json={"externalAiConsent": True})).status_code == 404


@pytest.mark.parametrize("failure", ["timeout", "http", "malformed", "truncated"])
async def test_finite_model_failure_preserves_screen_and_safe_diagnostics(
    case, monkeypatch, failure
):
    requests = []

    async def handler(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(f"private provider error api_key={SYNTHETIC_KEY}")
        if failure == "http":
            return httpx.Response(503, json={"error": f"api_key={SYNTHETIC_KEY}"})
        if failure == "truncated":
            return completion('{"items":[', finish_reason="length")
        return completion('{"items": "invalid shape"}')

    inject_provider(monkeypatch, handler, max_attempts=2 if failure == "http" else 1)
    started = await case.start()
    await case.execute(started)
    result = await case.result(started)
    assert result["status"] == "failed" and result["analysis"] is None
    assert result["failureKind"] and result["errorMessage"]
    assert len(requests) == 1
    assert SYNTHETIC_KEY not in json.dumps(result)
    assert "private provider error" not in json.dumps(result)
    assert result["inputPreflights"][0]["allowed"] is True
    if failure in {"malformed", "truncated"}:
        assert result["usage"]["inputTokens"] == 123
    original = await case.hr.post(f"/api/v1/applications/{case.application_id}/view")
    assert original.status_code == 200 and original.json()["data"]["report"] == case.snapshot
    assert (await case.hr.get(
        f"/api/v1/jobs/{case.job['id']}/applications"
    )).status_code == 200


async def test_creator_cache_and_task_reads_are_isolated_within_same_enterprise(case):
    coworker = AsyncClient(transport=ASGITransport(app=case.app), base_url="http://test")
    try:
        user = await register(coworker, "verification-coworker@example.com")
        async with case.factory() as session:
            session.add(EnterpriseMembership(
                enterprise_id=UUID(case.job["enterpriseId"]),
                user_id=UUID(user["id"]),
                role=MembershipRole.HR,
                is_active=True,
            ))
            await session.commit()
        first = await case.start()
        assert (await coworker.get(case.path)).json()["data"] is None
        assert (await coworker.get(f"{case.path}/{first['taskId']}")).status_code == 404
        assert (await coworker.get(
            f"/api/v1/analysis-tasks/{first['taskId']}"
        )).status_code == 404
        second = await case.start(coworker)
        assert second["taskId"] != first["taskId"] and not second["reused"]
        repeated = await case.start(coworker)
        assert repeated["taskId"] == second["taskId"] and repeated["reused"]
        assert (await case.hr.get(f"{case.path}/{second['taskId']}")).status_code == 404
    finally:
        await coworker.aclose()


async def test_different_application_cannot_reuse_or_read_another_task(case):
    second = AsyncClient(transport=ASGITransport(app=case.app), base_url="http://test")
    try:
        user = await register(second, "verification-second-student@example.com", "student")
        async with case.factory() as session:
            profile = await session.scalar(select(StudentProfile).where(
                StudentProfile.user_id == UUID(user["id"])
            ))
            source = await session.get(MatchReport, case.report_id)
            source_items = list(await session.scalars(select(MatchItem).where(
                MatchItem.report_id == source.id
            )))
            task = AnalysisTask(
                created_by=UUID(user["id"]), task_type="job_match", status=TaskStatus.COMPLETED
            )
            session.add(task)
            await session.flush()
            report = MatchReport(
                analysis_task_id=task.id,
                job_id=source.job_id,
                candidate_ref=str(profile.id),
                summary=source.summary,
                overall_score=source.overall_score,
                job_snapshot=deepcopy(source.job_snapshot),
                materials_snapshot=[],
            )
            session.add(report)
            await session.flush()
            for item in source_items:
                session.add(MatchItem(
                    report_id=report.id,
                    requirement_id=item.requirement_id,
                    rule_base_score=item.rule_base_score,
                    weight=item.weight,
                    final_score=item.final_score,
                    verdict=item.verdict,
                    explanation=item.explanation,
                    formula_version=item.formula_version,
                    evidence_snapshot=deepcopy(item.evidence_snapshot),
                ))
            await session.commit()
            report_id = report.id
        submitted = await second.post(
            "/api/v1/applications", json={"reportId": str(report_id), "shareConsent": True}
        )
        assert submitted.status_code == 201, submitted.text
        application_id = submitted.json()["data"]["id"]
        path = f"/api/v1/applications/{application_id}/verification"
        first = await case.start()
        assert (await case.hr.get(f"{path}/{first['taskId']}")).status_code == 404
        created = await case.hr.post(path, json={"externalAiConsent": True})
        assert created.status_code == 202, created.text
        second_task = created.json()["data"]
        assert second_task["taskId"] != first["taskId"] and not second_task["reused"]
        assert (await case.hr.get(
            f"{case.path}/{second_task['taskId']}"
        )).status_code == 404
    finally:
        await second.aclose()


@pytest.mark.parametrize("invalid", [
    "missing_requirement", "duplicate_requirement", "unknown_requirement",
    "unknown_citation", "cross_requirement", "empty_citations", "reference_support",
    "missing_support", "score", "hiring_decision", "unpaired_next_step",
])
async def test_verification_output_guard_rejects_unscoped_or_unproved_advice(case, invalid):
    answer, snapshot = model_answer(case.snapshot), deepcopy(case.snapshot)
    first = answer["items"][0]
    if invalid == "missing_requirement":
        answer["items"].pop()
    elif invalid == "duplicate_requirement":
        answer["items"].append(deepcopy(first))
    elif invalid == "unknown_requirement":
        first["requirementId"] = str(uuid4())
    elif invalid == "unknown_citation":
        first["citationIds"] = ["R404-E1"]
    elif invalid == "cross_requirement":
        first["citationIds"] = ["R3-E1"]
    elif invalid == "empty_citations":
        first["citationIds"] = []
    elif invalid == "reference_support":
        snapshot["items"][0]["evidenceList"][0]["provenance"] = "reference"
    elif invalid == "missing_support":
        answer["items"][1]["visibleSupport"] = "材料证明存在本人实现。"
    elif invalid == "score":
        first["hiringScore"] = 90
    elif invalid == "hiring_decision":
        first["nextStep"] = "request_evidence"
        first["nextStepReason"] = "建议录用该候选人。"
    else:
        first["nextStep"] = "request_evidence"
    with pytest.raises(ValueError):
        verification.validate_verification(answer, snapshot)


async def test_outbound_context_and_saved_diagnostics_redact_credentials(case, monkeypatch):
    private = "sk-synthetic-source-secret-000002"
    changed = deepcopy(case.snapshot)
    changed["candidateName"] = "仅用于隐私核验的姓名"
    changed["items"][0]["evidenceList"][0]["snippet"] += (
        f'api_key = "{private}"\n# owner@example.com 13800138000\n'
    )
    async with case.factory() as session:
        application = await session.get(Application, UUID(case.application_id))
        application.report_snapshot = changed
        await session.commit()
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert private not in request.content.decode()
        assert "owner@example.com" not in request.content.decode()
        assert "13800138000" not in request.content.decode()
        assert changed["candidateName"] not in request.content.decode()
        answer = model_answer(changed)
        answer["items"][0]["informationGap"] += f" api_key={private}"
        return completion(answer)

    inject_provider(monkeypatch, handler)
    started = await case.start()
    await case.execute(started)
    result = await case.result(started)
    assert result["status"] == "completed"
    assert private not in json.dumps(result) and SYNTHETIC_KEY not in json.dumps(result)
    assert "redacted credential" in result["analysis"]["items"][0]["informationGap"]
    assert requests and result["usage"]["inputTokens"] == 123
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        saved = json.dumps(task.input_snapshot, ensure_ascii=False)
        assert private not in saved and SYNTHETIC_KEY not in saved
        assert "return sum(values)" not in saved
        assert "fixedReportRequirements" not in saved
        # The original frozen material remains intact; sanitization touches copies.
        application = await session.get(Application, UUID(case.application_id))
        assert private in application.report_snapshot["items"][0]["evidenceList"][0]["snippet"]


async def test_withdrawal_waiting_for_model_semaphore_blocks_presend(case, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    class Gate:
        async def __aenter__(self):
            entered.set()
            await release.wait()

        async def __aexit__(self, *_exception):
            return False

    monkeypatch.setattr(verification, "_model_semaphore", Gate)

    async def handler(request):
        calls.append(request)
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    work = asyncio.create_task(case.execute(started))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert (await case.student.post(
            f"/api/v1/applications/{case.application_id}/withdraw"
        )).status_code == 200
    finally:
        release.set()
        await asyncio.wait_for(work, 5)
    assert calls == []
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.CANCELLED
        assert task.input_snapshot["failureKind"] == "authorization_revoked"


async def test_model_wait_does_not_hold_creator_lock_and_withdrawal_cancels_result(
    case, monkeypatch
):
    if case.factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires an explicitly configured isolated PostgreSQL schema")
    entered, release = asyncio.Event(), asyncio.Event()

    async def handler(_request):
        entered.set()
        await release.wait()
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    work = asyncio.create_task(case.execute(started))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        async with case.factory() as observer:
            creator = await observer.scalar(
                select(AnalysisTask.created_by).where(AnalysisTask.id == UUID(started["taskId"]))
            )
            # NOWAIT would fail if the budget transaction still held this row.
            assert await observer.scalar(
                select(User.id).where(User.id == creator).with_for_update(nowait=True)
            ) == creator
            await observer.rollback()
        assert (await case.student.post(
            f"/api/v1/applications/{case.application_id}/withdraw"
        )).status_code == 200
    finally:
        release.set()
        await asyncio.wait_for(work, 5)
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.CANCELLED
        assert task.input_snapshot["analysis"] is None


async def test_postgres_observed_account_lock_wait_rechecks_withdrawal_before_model(
    case, monkeypatch
):
    if case.factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires an explicitly configured isolated PostgreSQL schema")
    at_budget = asyncio.Event()
    from app.services.ai_request_attempts import AttemptService
    original_identity = AttemptService._live_identity
    waiter_pid = None
    calls = []

    async def budget_probe(self, session):
        nonlocal waiter_pid
        waiter_pid = await session.scalar(text("SELECT pg_backend_pid()"))
        at_budget.set()
        return await original_identity(self, session)

    async def handler(request):
        calls.append(request)
        return completion(model_answer(case.snapshot))

    monkeypatch.setattr(AttemptService, "_live_identity", budget_probe)
    inject_provider(monkeypatch, handler)
    started = await case.start()
    work = None
    try:
        async with case.factory() as blocker, blocker.begin():
            creator = await blocker.scalar(select(AnalysisTask.created_by).where(
                AnalysisTask.id == UUID(started["taskId"])
            ))
            # Match the budget lock: it must block another budget check while
            # allowing withdrawal notices to reference the enterprise user.
            await blocker.scalar(
                select(User).where(User.id == creator).with_for_update(key_share=True)
            )
            blocker_pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
            work = asyncio.create_task(case.execute(started))
            await asyncio.wait_for(at_budget.wait(), 5)
            async with case.factory() as observer, asyncio.timeout(5):
                observed = False
                while not observed:
                    await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                    observed = bool(await observer.scalar(text(
                        "SELECT wait_event_type = 'Lock' AND "
                        ":blocker = ANY(pg_blocking_pids(pid)) "
                        "FROM pg_stat_activity WHERE pid = :waiter"
                    ), {"blocker": blocker_pid, "waiter": waiter_pid}))
                    if not observed:
                        await asyncio.sleep(0.01)
            assert observed and not work.done() and calls == []
            assert (await case.student.post(
                f"/api/v1/applications/{case.application_id}/withdraw"
            )).status_code == 200
        await asyncio.wait_for(work, 5)
    finally:
        if work is not None and not work.done():
            work.cancel()
            await asyncio.gather(work, return_exceptions=True)
    assert calls == []
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.CANCELLED
        assert task.input_snapshot["analysis"] is None


@pytest.mark.parametrize("mode", ["failure", "snapshot_change"])
async def test_creator_application_throttle_cannot_be_bypassed_with_failure_or_hash_change(
    case, monkeypatch, mode
):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(503, json={"error": "合成故障"})

    inject_provider(monkeypatch, handler)
    for number in range(3):
        started = await case.start()
        if mode == "failure":
            await case.execute(started)
            assert (await case.result(started))["status"] == "failed"
        else:
            repeated = await case.start()
            assert repeated["taskId"] == started["taskId"] and repeated["reused"]
            async with case.factory() as session:
                application = await session.get(Application, UUID(case.application_id))
                snapshot = deepcopy(application.report_snapshot)
                snapshot["summary"] = f"合成快照变化 {number}"
                application.report_snapshot = snapshot
                await session.commit()
    limited = await case.hr.post(case.path, json={"externalAiConsent": True})
    assert limited.status_code == 429, limited.text
    assert len(requests) == (3 if mode == "failure" else 0)
    async with case.factory() as session:
        tasks = list(await session.scalars(select(AnalysisTask).where(
            AnalysisTask.task_type == "application_verification"
        )))
        assert len(tasks) == 3


async def test_input_preflight_blocks_network_and_preserves_numeric_budget_diagnostic(
    case, monkeypatch
):
    requests = []

    async def handler(request):
        requests.append(request)
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", 1000)
    started = await case.start()
    await case.execute(started)
    result = await case.result(started)
    assert result["status"] == "failed" and result["failureKind"] == "input_budget"
    assert result["usage"] is None and requests == []
    preflight = result["inputPreflights"][0]
    assert preflight["allowed"] is False and preflight["remainingInputBudget"] == 1000
    assert preflight["estimatedInputBound"] > preflight["remainingInputBudget"]
    assert preflight["estimateMethod"] == "json-character-upper-bound"
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        stop = task.input_snapshot["inputBudgetStop"]
        assert stop["estimatedInputBound"] == preflight["estimatedInputBound"]
        assert stop["remainingInputBudget"] == 1000
        assert list(await session.scalars(select(AiUsageLog).where(
            AiUsageLog.analysis_task_id == task.id
        ))) == []


async def test_transient_provider_failure_never_resends_the_snapshot(case, monkeypatch):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(503, json={"error": "synthetic unavailable"})

    inject_provider(monkeypatch, handler, max_attempts=3)
    started = await case.start()
    await case.execute(started)
    result = await case.result(started)
    assert result["status"] == "failed" and result["failureKind"] == "provider_http_503"
    assert len(requests) == 1 and result["analysis"] is None


@pytest.mark.parametrize("corruption", ["missing", "not-a-uuid", None])
async def test_unusable_application_reference_ends_claimed_task_with_explicit_failure(
    case, corruption
):
    started = await case.start()
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        saved = dict(task.input_snapshot)
        if corruption == "missing":
            saved.pop("applicationId")
        else:
            saved["applicationId"] = corruption
        task.input_snapshot = saved
        await session.commit()

    await case.execute(started)

    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.FAILED
        assert task.error_message
        saved = task.input_snapshot
        assert saved["failureKind"] == "configuration_or_invalid_output"
        assert saved["aiStatus"] == "configuration_or_invalid_output"
        assert saved["analysis"] is None and saved["usage"] is None
        assert list(await session.scalars(select(AiUsageLog).where(
            AiUsageLog.analysis_task_id == task.id
        ))) == []
        steps = list(await session.scalars(select(AgentStep).where(
            AgentStep.analysis_task_id == task.id
        )))
        assert [step.event_type for step in steps] == ["verification.unavailable"]


@pytest.mark.parametrize("read_path", ["latest", "result", "task"])
async def test_postgres_saved_read_serializes_with_withdrawal(case, monkeypatch, read_path):
    if case.factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires an explicitly configured isolated PostgreSQL schema")
    inject_provider(monkeypatch, lambda request: completion(model_answer(case.snapshot)))
    started = await case.start()
    await case.execute(started)
    paths = {
        "latest": case.path,
        "result": f"{case.path}/{started['taskId']}",
        "task": f"/api/v1/analysis-tasks/{started['taskId']}",
    }
    path = paths[read_path]
    entered, release = asyncio.Event(), asyncio.Event()
    original = verification._authorized
    holder_pid = None

    async def paused_access(session, application_id, user_id, *, lock=False):
        nonlocal holder_pid
        result = await original(session, application_id, user_id, lock=lock)
        assert lock is True, "Saved-result access must hold the short application lock"
        holder_pid = await session.scalar(text("SELECT pg_backend_pid()"))
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(verification, "_authorized", paused_access)
    read = asyncio.create_task(case.hr.get(path))
    withdrawal = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        withdrawal = asyncio.create_task(case.student.post(
            f"/api/v1/applications/{case.application_id}/withdraw"
        ))
        async with case.factory() as observer, asyncio.timeout(5):
            observed = False
            while not observed:
                await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                observed = bool(await observer.scalar(text(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE "
                    "wait_event_type = 'Lock' AND :holder = ANY(pg_blocking_pids(pid)))"
                ), {"holder": holder_pid}))
                if not observed:
                    await asyncio.sleep(0.01)
        assert observed and not withdrawal.done()
        release.set()
        assert (await asyncio.wait_for(read, 5)).status_code == 200
        assert (await asyncio.wait_for(withdrawal, 5)).status_code == 200
    finally:
        release.set()
        for work in (read, withdrawal):
            if work is not None and not work.done():
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
    assert (await case.hr.get(path)).status_code == 404
