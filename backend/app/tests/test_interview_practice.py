"""Interview practice: one requirement, fixed citations, no duplicate model calls.

All model traffic is a local stub. No test reads a real provider or writes a
report verdict, growth draft or application.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.knowledge.technical_seed import TECHNICAL_KNOWLEDGE, content_digest
from app.models.analysis import AiUsageLog, AnalysisTask, MatchItem, MatchReport
from app.models.enums import TaskStatus
from app.models.growth_answer import GrowthAnswerDraft
from app.models.identity import StudentProfile
from app.models.knowledge import TechnicalKnowledgeEntry
from app.models.portfolio import InterviewAnswer, InterviewSession
from app.models.recruitment import Job, JobRequirement
from app.services import interview_practice as practice
from app.services.task_dispatcher import dispatch_pending_tasks, wait_for_dispatched_tasks
from app.services.task_lifecycle import recover_interrupted_tasks
from app.services.technical_knowledge import rank_entries, seed_technical_knowledge
from app.tests.test_jobs_api import register

pytest_plugins = ["app.tests.test_jobs_api", "app.tests.test_real_matching"]


@pytest.fixture
def practice_db(matching_db):
    return matching_db


EVIDENCE = {
    "citation_id": "R3-E1",
    "file_path": "version-1/test_pipeline.py",
    "line_start": 3,
    "line_end": 4,
    "snippet": 'def test_clean():\n    assert clean([" a ", ""]) == ["a"]',
    "content_hash": "a" * 64,
    "provenance": "portfolio",
    "project_version_id": "version-1",
}
SQL_ITEM = {
    "skill": "SQL",
    "requirementTitle": "使用 SQL JOIN 核查金额翻倍的原因",
    "claimed": True,
    "claimText": "简历声明会写 SQL",
    "evidenceList": [],
}
PYTEST_ITEM = {
    "skill": "pytest",
    "requirementTitle": "编写可复现的 pytest 测试",
    "claimed": True,
    "claimText": "简历声明写过 pytest",
    "evidenceList": [EVIDENCE],
}


class StubProvider:
    name = "stub"
    model = "stub-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.usage = SimpleNamespace(
            input_tokens=120, output_tokens=80, cache_hit_tokens=0, latency_ms=90
        )

    async def generate_bounded_json(self, *, system, data, max_tokens=1400):
        self.calls.append({"system": system, "data": data, "maxTokens": max_tokens})
        if not self.responses:
            raise AssertionError("unexpected model call")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def combined_usage(self):
        return self.usage


def question(text, citation_ids=(), knowledge_ids=(), focus="实现细节"):
    return {
        "question": text,
        "focus": focus,
        "citationIds": list(citation_ids),
        "knowledgeIds": list(knowledge_ids),
    }


def feedback(
    covered,
    citation_ids=(),
    knowledge_ids=(),
    missing=(),
    follow_up="追问：如果输入是空列表，你的断言会怎样？",
    question_quote="你还需要补哪些边界",
):
    return {
        "findings": [
            {"point": text, "kind": kind, "text": text,
             **({"questionQuote": question_quote} if kind == "missing" else {})}
            for kind, values in (("covered", covered), ("missing", missing))
            for text in values
        ],
        "reviewSuggestion": "补充一条边界输入，并写出期望结果。",
        "followUp": follow_up,
        "citationIds": list(citation_ids),
        "knowledgeIds": list(knowledge_ids),
    }


async def seed(factory, user_id: str, *, item_snapshot: dict, skill: str, verdict: str):
    async with factory() as session:
        profile = await session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == UUID(user_id))
        )
        job = Job(
            created_by=UUID(user_id),
            title="数据工程实习生",
            company_name="合成企业",
            status="published",
        )
        session.add(job)
        await session.flush()
        requirement = JobRequirement(
            job_id=job.id,
            raw_text=item_snapshot["requirementTitle"],
            skill_name=skill,
            weight=4,
            is_required=True,
            normalized_status="normalized",
        )
        session.add(requirement)
        await session.flush()
        task = AnalysisTask(
            created_by=UUID(user_id), task_type="job_match", status=TaskStatus.COMPLETED
        )
        session.add(task)
        await session.flush()
        report = MatchReport(
            analysis_task_id=task.id,
            job_id=job.id,
            candidate_ref=user_id,
            candidate_name="合成学生",
            summary="合成报告",
            overall_score=60,
            job_snapshot={"title": job.title, "category": "software"},
            materials_snapshot=[
                {
                    "kind": "project",
                    "id": "version-1",
                    "title": "数据清洗脚本",
                    "versionNumber": 2,
                    "contentHash": "b" * 64,
                    "materialRole": "portfolio",
                }
            ],
            gaps=[],
            claimed_only=[],
        )
        session.add(report)
        await session.flush()
        item = MatchItem(
            report_id=report.id,
            requirement_id=requirement.id,
            rule_base_score=1,
            weight=4,
            verdict=verdict,
            explanation="规则判断原文",
            formula_version="rule-v1",
            evidence_snapshot=item_snapshot,
        )
        session.add(item)
        await seed_technical_knowledge(session)
        await session.commit()
        return str(report.id), str(requirement.id), str(profile.id)


class SettledPracticeClient(AsyncClient):
    def __init__(self, app, factory):
        super().__init__(transport=ASGITransport(app=app), base_url="http://test")
        self.factory = factory

    async def post(self, url, **kwargs):
        response = await super().post(url, **kwargs)
        if (
            response.status_code == 200
            and url.startswith("/api/v1/interview-sessions/")
            and await dispatch_pending_tasks(self.factory)
        ):
            await wait_for_dispatched_tasks()
            return await self.get("/".join(url.split("/")[:5]))
        return response


async def client_for(app, factory=None):
    if factory:
        return SettledPracticeClient(app, factory)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def open_session(client, report_id, requirement_id):
    response = await client.post(
        f"/api/v1/match-reports/{report_id}/interview-sessions",
        json={"requirementId": requirement_id},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["session"]


def use_provider(monkeypatch, responses):
    provider = StubProvider(responses)
    monkeypatch.setattr(practice, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(practice, "OpenAICompatibleProvider", StubProvider)
    return provider


async def test_python_evidence_runs_two_turns_and_persists_summary(practice_db, monkeypatch):
    app, factory = practice_db
    student = await client_for(app, factory)
    user = await register(student, "practice-a@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=PYTEST_ITEM, skill="pytest", verdict="supported"
    )

    async with factory() as session:
        report = await session.get(MatchReport, UUID(report_id))
        job_id = str(report.job_id)
        knowledge = list(
            await session.scalars(
                select(TechnicalKnowledgeEntry).where(TechnicalKnowledgeEntry.skill == "pytest")
            )
        )
        knowledge_id = knowledge[0].knowledge_id

    provider = use_provider(
        monkeypatch,
        [
            question(
                "材料里 test_clean 只覆盖了一条正常输入，你还需要补哪些边界？",
                ["R3-E1"],
                [knowledge_id],
                focus="测试边界",
            ),
            feedback(
                ["说明了现有断言只覆盖正常输入"],
                ["R3-E1"],
                [knowledge_id],
                missing=["没有说明异常输入的断言"],
            ),
            feedback(
                ["补充了空列表边界"], [], [knowledge_id], follow_up="追问：异常输入怎么断言？"
            ),
        ],
    )

    opened = await open_session(student, report_id, requirement_id)
    assert opened["status"] == "draft"
    assert opened["jobId"] == job_id
    assert opened["evidence"][0]["citationId"] == "R3-E1"
    assert opened["knowledge"][0]["knowledgeId"] == knowledge_id
    assert opened["turns"] == []
    # Pre-answer payload must not carry reference points or principles.
    serialized = json.dumps(opened, ensure_ascii=False)
    assert "referencePoints" not in serialized and "principle" not in serialized

    refused = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/start",
        json={"externalAiConsent": False},
    )
    assert refused.status_code == 422
    assert provider.calls == []

    started = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/start", json={"externalAiConsent": True}
    )
    assert started.status_code == 200, started.text
    first = started.json()["data"]
    assert first["turns"][0]["state"] == "question"
    assert first["turns"][0]["answerText"] is None
    assert first["turns"][0]["feedback"] is None
    assert first["turns"][0]["citations"][0]["filePath"].endswith("test_pipeline.py")

    answered = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/turns/0/answers",
        json={"answerText": "我会补空列表和 None 两个边界。", "clientToken": "token-0001"},
    )
    assert answered.status_code == 200, answered.text
    after_first = answered.json()["data"]
    assert after_first["turns"][0]["state"] == "feedback"
    assert after_first["turns"][0]["feedback"]["citations"][0]["lineStart"] == 3
    assert after_first["turns"][1]["state"] == "question"
    assert after_first["turns"][1]["kind"] == "follow_up"
    assert after_first["summary"] is None

    finished = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/turns/1/answers",
        json={
            "answerText": "异常输入用 pytest.raises 断言 ValueError。",
            "clientToken": "token-0002",
        },
    )
    assert finished.status_code == 200, finished.text
    done = finished.json()["data"]
    assert done["status"] == "completed"
    assert done["summary"]["answeredTurns"] == 2
    assert done["summary"]["nextStep"]
    assert len(provider.calls) == 3

    reopened = await student.get(f"/api/v1/interview-sessions/{opened['id']}")
    assert reopened.status_code == 200
    again = reopened.json()["data"]
    assert [turn["question"] for turn in again["turns"]] == [
        turn["question"] for turn in done["turns"]
    ]
    assert again["summary"] == done["summary"]

    async with factory() as session:
        turns = list(
            await session.scalars(
                select(InterviewAnswer).where(InterviewAnswer.session_id == UUID(opened["id"]))
            )
        )
        assert len(turns) == 2
        # Each saved turn records the model that produced it, so a reopened practice can be
        # traced back to the provider that generated the question and the critique.
        assert all(turn.ai_model == "stub-model" for turn in turns)
        usage = list(await session.scalars(select(AiUsageLog)))
        assert usage and all(row.model == "stub-model" for row in usage)
        tasks = list(
            await session.scalars(
                select(AnalysisTask).where(AnalysisTask.task_type == "interview_practice")
            )
        )
        assert len(tasks) == 3 and all(task.status == TaskStatus.COMPLETED for task in tasks)
        assert list(await session.scalars(select(GrowthAnswerDraft))) == []


async def test_sql_claim_only_cannot_borrow_code_or_citations(practice_db, monkeypatch):
    app, factory = practice_db
    student = await client_for(app, factory)
    user = await register(student, "practice-sql@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=SQL_ITEM, skill="SQL", verdict="claimed_only"
    )
    async with factory() as session:
        knowledge_id = await session.scalar(
            select(TechnicalKnowledgeEntry.knowledge_id).where(
                TechnicalKnowledgeEntry.knowledge_id == "tech-sql-join-grain"
            )
        )

    provider = use_provider(
        monkeypatch,
        [
            question("如果 CSV 里编码不一致，你会怎样定位并修正？", ["R3-E1"], [knowledge_id]),
            question("一张订单表关联明细后金额翻倍，你会怎样排查？", [], [knowledge_id]),
            feedback(["说明了先确认行数变化"], ["R3-E1"], [knowledge_id]),
            feedback(["说明了先确认 JOIN 前后的行数"], [], [knowledge_id]),
        ],
    )

    opened = await open_session(student, report_id, requirement_id)
    assert opened["evidence"] == []
    rejected = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/start", json={"externalAiConsent": True}
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["questionTask"]["status"] == "failed"
    assert rejected.json()["data"]["turns"] == []
    async with factory() as session:
        assert list(await session.scalars(select(InterviewAnswer))) == []
        failed = await session.scalar(
            select(AnalysisTask).where(AnalysisTask.task_type == "interview_practice")
        )
        assert failed is not None and failed.status == TaskStatus.FAILED

    started = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/start", json={"externalAiConsent": True}
    )
    assert started.status_code == 200, started.text
    assert started.json()["data"]["turns"][0]["citations"] == []

    bad = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/turns/0/answers",
        json={"answerText": "我会先看编码声明，再用示例行验证。", "clientToken": "token-sql-1"},
    )
    assert bad.status_code == 200, bad.text
    turn = bad.json()["data"]["turns"][0]
    assert turn["state"] == "failed"
    assert turn["answerText"] == "我会先看编码声明，再用示例行验证。"
    assert "没有材料引用" in (turn["failureReason"] or "") or "校验" in (
        turn["failureReason"] or ""
    )
    assert len(provider.calls) == 3

    retried = await student.post(f"/api/v1/interview-sessions/{opened['id']}/turns/0/retry")
    assert retried.status_code == 200, retried.text
    recovered = retried.json()["data"]["turns"][0]
    assert recovered["state"] == "feedback"
    assert recovered["feedback"]["citations"] == []
    assert recovered["feedback"]["covered"]


async def test_duplicate_submit_and_retry_never_double_call(practice_db, monkeypatch):
    app, factory = practice_db
    student = await client_for(app, factory)
    user = await register(student, "practice-dup@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=PYTEST_ITEM, skill="pytest", verdict="supported"
    )
    async with factory() as session:
        knowledge_id = await session.scalar(
            select(TechnicalKnowledgeEntry.knowledge_id).where(
                TechnicalKnowledgeEntry.skill == "pytest"
            )
        )

    provider = use_provider(
        monkeypatch,
        [
            question("这条断言能证明哪些边界？", ["R3-E1"], [knowledge_id]),
            feedback(["指出了断言范围"], ["R3-E1"], [knowledge_id]),
            feedback(["第二轮补充"], [], [knowledge_id]),
        ],
    )
    opened = await open_session(student, report_id, requirement_id)
    await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/start", json={"externalAiConsent": True}
    )
    calls_before = len(provider.calls)

    first = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/turns/0/answers",
        json={"answerText": "只覆盖了正常输入。", "clientToken": "token-dup"},
    )
    second = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/turns/0/answers",
        json={"answerText": "重复提交不应再调用模型。", "clientToken": "token-dup"},
    )
    assert first.status_code == second.status_code == 200
    assert len(provider.calls) == calls_before + 1
    assert second.json()["data"]["turns"][0]["answerText"] == "只覆盖了正常输入。"

    retry = await student.post(f"/api/v1/interview-sessions/{opened['id']}/turns/0/retry")
    assert retry.status_code == 200
    assert len(provider.calls) == calls_before + 1
    assert retry.json()["data"]["turns"][0]["state"] == "feedback"


@pytest.mark.parametrize(
    ("failed_output", "notice", "diagnostic"),
    [
        (TimeoutError(), "超时", "stage=provider reason=TimeoutError"),
        (ValueError("private-provider-detail"), "未通过校验", "stage=provider reason=ValueError"),
        (
            feedback(["断言范围"], missing=["断言范围"]),
            "未通过校验",
            "stage=output_validation reason=同一问点只能有一种点评",
        ),
    ],
)
async def test_ai_failure_keeps_answer_and_retry_completes(
    practice_db, monkeypatch, caplog, failed_output, notice, diagnostic
):
    app, factory = practice_db
    student = await client_for(app, factory)
    user = await register(student, "practice-fail@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=PYTEST_ITEM, skill="pytest", verdict="supported"
    )
    async with factory() as session:
        knowledge_id = await session.scalar(
            select(TechnicalKnowledgeEntry.knowledge_id).where(
                TechnicalKnowledgeEntry.skill == "pytest"
            )
        )
    use_provider(
        monkeypatch,
        [
            question("这条断言覆盖了哪些输入？", ["R3-E1"], [knowledge_id]),
            failed_output,
            feedback(["回答了断言范围"], ["R3-E1"], [knowledge_id]),
            feedback(["追问回答"], [], [knowledge_id]),
        ],
    )
    opened = await open_session(student, report_id, requirement_id)
    await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/start", json={"externalAiConsent": True}
    )

    failed = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/turns/0/answers",
        json={"answerText": "只覆盖了正常输入。", "clientToken": "token-fail"},
    )
    assert failed.status_code == 200
    turn = failed.json()["data"]["turns"][0]
    assert turn["state"] == "failed"
    assert turn["answerText"] == "只覆盖了正常输入。"
    assert turn["feedback"] is None
    assert notice in turn["failureReason"]
    assert f"task_id={turn['feedbackTask']['id']} operation=feedback {diagnostic}" in caplog.text
    assert "private-provider-detail" not in caplog.text
    assert turn["answerText"] not in caplog.text

    read = await student.get(f"/api/v1/interview-sessions/{opened['id']}")
    assert read.json()["data"]["turns"][0]["answerText"] == "只覆盖了正常输入。"

    retried = await student.post(f"/api/v1/interview-sessions/{opened['id']}/turns/0/retry")
    assert retried.status_code == 200
    assert retried.json()["data"]["turns"][0]["state"] == "feedback"


async def test_other_student_cannot_read_or_continue(practice_db, monkeypatch):
    app, factory = practice_db
    owner = await client_for(app, factory)
    stranger = await client_for(app, factory)
    user = await register(owner, "practice-owner@example.com", "student")
    await register(stranger, "practice-stranger@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=PYTEST_ITEM, skill="pytest", verdict="supported"
    )
    use_provider(monkeypatch, [])
    opened = await open_session(owner, report_id, requirement_id)

    assert (await stranger.get(f"/api/v1/interview-sessions/{opened['id']}")).status_code == 404
    assert (
        await stranger.post(
            f"/api/v1/interview-sessions/{opened['id']}/start", json={"externalAiConsent": True}
        )
    ).status_code == 404
    assert (
        await stranger.post(
            f"/api/v1/interview-sessions/{opened['id']}/turns/0/answers",
            json={"answerText": "越权", "clientToken": "token-stranger"},
        )
    ).status_code == 404


async def test_practice_does_not_rewrite_report_or_start_new_sessions(practice_db, monkeypatch):
    app, factory = practice_db
    student = await client_for(app, factory)
    user = await register(student, "practice-frozen@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=PYTEST_ITEM, skill="pytest", verdict="supported"
    )
    async with factory() as session:
        knowledge_id = await session.scalar(
            select(TechnicalKnowledgeEntry.knowledge_id).where(
                TechnicalKnowledgeEntry.skill == "pytest"
            )
        )
    use_provider(
        monkeypatch,
        [
            question("这条断言覆盖了哪些输入？", ["R3-E1"], [knowledge_id]),
            feedback(["回答了断言范围"], ["R3-E1"], [knowledge_id]),
            feedback(["追问回答"], [], [knowledge_id]),
        ],
    )

    first = await open_session(student, report_id, requirement_id)
    resumed = await open_session(student, report_id, requirement_id)
    assert resumed["id"] == first["id"]

    async with factory() as session:
        report = await session.scalar(select(MatchReport).where(MatchReport.id == UUID(report_id)))
        item = await session.scalar(select(MatchItem).where(MatchItem.report_id == UUID(report_id)))
        assert report.version == 1
        assert item.verdict == "supported"
        assert item.explanation == "规则判断原文"
        assert (
            list(await session.scalars(select(InterviewSession)))
            and len(list(await session.scalars(select(InterviewSession)))) == 1
        )


def test_question_validation_accepts_a_question_closed_with_a_period():
    """A model may end a real question with 。; punctuation alone must not fail it."""

    result = practice.validate_question(
        {
            "question": (
                "材料里的 clean 只对字符串做了 strip。如果某行是 None，会怎样调整异常处理"
                "边界，让坏行被跳过并且事后可查。"
            ),
            "focus": "异常边界与失败行记录",
            "citationIds": ["R3-E1"],
            "knowledgeIds": [],
        },
        allowed_citations={"R3-E1"},
        allowed_knowledge=set(),
        has_evidence=True,
    )
    assert result["citationIds"] == ["R3-E1"]
    assert result["question"].endswith("。")


def test_question_validation_rejects_a_statement_and_an_out_of_scope_citation():
    with pytest.raises(ValueError):
        practice.validate_question(
            {
                "question": "这段代码展示了列表推导与 strip 的常见组合写法。",
                "focus": "",
                "citationIds": [],
                "knowledgeIds": [],
            },
            allowed_citations={"R3-E1"},
            allowed_knowledge=set(),
            has_evidence=True,
        )
    with pytest.raises(ValueError):
        practice.validate_question(
            {
                "question": "材料里的 clean 如何处理 None？",
                "focus": "",
                "citationIds": ["R9-E9"],
                "knowledgeIds": [],
            },
            allowed_citations={"R3-E1"},
            allowed_knowledge=set(),
            has_evidence=True,
        )


async def test_new_sql_session_uses_corrected_aggregate_null_snapshot(practice_db, monkeypatch):
    app, factory = practice_db
    student = await client_for(app, factory)
    user = await register(student, "practice-sql-aggregate@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory,
        user["id"],
        item_snapshot={**SQL_ITEM, "requirementTitle": "核对 COUNT(*) 与 AVG(score) 的 NULL 口径"},
        skill="SQL",
        verdict="claimed_only",
    )
    seed_entry = next(
        item for item in TECHNICAL_KNOWLEDGE if item["knowledge_id"] == "tech-sql-aggregate-null"
    )
    opened = await open_session(student, report_id, requirement_id)
    assert opened["knowledgeOutdated"] is False
    async with factory() as session:
        row = await session.scalar(
            select(InterviewSession).where(InterviewSession.id == UUID(opened["id"]))
        )
        entry = next(
            item
            for item in row.knowledge_snapshot
            if item["knowledgeId"] == "tech-sql-aggregate-null"
        )
    assert entry["contentHash"] == content_digest(seed_entry)
    assert "array_agg" in entry["principle"] and "COUNT(*)" in entry["principle"]
    provider = use_provider(
        monkeypatch,
        [
            question(
                "COUNT(col) 和 COUNT(*) 在 NULL 口径上有什么不同？",
                [],
                ["tech-sql-aggregate-null"],
            )
        ],
    )
    started = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/start", json={"externalAiConsent": True}
    )
    assert started.status_code == 200, started.text
    payload = provider.calls[0]["data"]["knowledge"]
    supplied = next(item for item in payload if item["knowledgeId"] == "tech-sql-aggregate-null")
    assert "array_agg" in supplied["principle"]
    assert "不能" in supplied["principle"] and "偏高" in supplied["principle"]


async def test_outdated_knowledge_session_is_read_only_and_restart_gets_current_snapshot(
    practice_db, monkeypatch
):
    app, factory = practice_db
    student = await client_for(app, factory)
    user = await register(student, "practice-sql-stale@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory,
        user["id"],
        item_snapshot={**SQL_ITEM, "requirementTitle": "核对 COUNT(*) 与 AVG(score) 的 NULL 口径"},
        skill="SQL",
        verdict="claimed_only",
    )
    opened = await open_session(student, report_id, requirement_id)
    async with factory() as session:
        row = await session.scalar(
            select(InterviewSession).where(InterviewSession.id == UUID(opened["id"]))
        )
        snapshot = [dict(item) for item in row.knowledge_snapshot]
        old = next(item for item in snapshot if item["knowledgeId"] == "tech-sql-aggregate-null")
        old["title"] = "旧版错误标题"
        old["contentHash"] = "0" * 64
        row.knowledge_snapshot = snapshot
        await session.commit()
    stale_view = await student.get(f"/api/v1/interview-sessions/{opened['id']}")
    assert stale_view.status_code == 200
    stale_data = stale_view.json()["data"]
    assert stale_data["knowledgeOutdated"] is True
    assert any(item["title"] == "旧版错误标题" for item in stale_data["knowledge"])
    provider = use_provider(monkeypatch, [])
    blocked = await student.post(
        f"/api/v1/interview-sessions/{opened['id']}/start", json={"externalAiConsent": True}
    )
    assert blocked.status_code == 409
    assert "知识依据已更新" in blocked.text
    assert provider.calls == []
    restarted = await student.post(
        f"/api/v1/match-reports/{report_id}/interview-sessions",
        json={"requirementId": requirement_id, "restart": True},
    )
    assert restarted.status_code == 200, restarted.text
    new_id = restarted.json()["data"]["session"]["id"]
    assert new_id != opened["id"]
    async with factory() as session:
        row = await session.scalar(
            select(InterviewSession).where(InterviewSession.id == UUID(new_id))
        )
        entry = next(
            item
            for item in row.knowledge_snapshot
            if item["knowledgeId"] == "tech-sql-aggregate-null"
        )
    assert entry["contentHash"] != "0" * 64
    assert "旧版错误标题" not in entry["title"]


@pytest.mark.parametrize(
    ("skill", "query", "expected"),
    [
        ("Python", "处理 Python 缺失值和空字符串", "tech-python-missing-values"),
        ("pytest", "使用 pytest 检查异常类型", "tech-pytest-raises-boundary"),
        ("pytest", "使用 pytest.raises 检查", "tech-pytest-raises-boundary"),
        ("SQL", "使用 SQL 分组过滤聚合结果", "tech-sql-where-having"),
        ("SQL", "使用 SQL 核查异常结果", "tech-sql-aggregate-null"),
        ("SQL", "比较 WHERE 与 HAVING", "tech-sql-where-having"),
    ],
)
def test_concrete_knowledge_topic_beats_family(skill, query, expected):
    entries = [
        TechnicalKnowledgeEntry(**item, content_hash=content_digest(item))
        for item in TECHNICAL_KNOWLEDGE
    ]
    assert rank_entries(entries, skill=skill, text=query)[0].knowledge_id == expected
    assert rank_entries(entries, skill=skill, text="如何折叠纸飞机") == []


async def test_seed_refreshes_fields_and_old_digest_does_not_expire_session(
    practice_db, monkeypatch
):
    from app.services import technical_knowledge

    app, factory = practice_db
    async with await client_for(app) as student:
        user = await register(student, "practice-refresh@example.com", "student")
        report_id, requirement_id, _ = await seed(
            factory, user["id"], item_snapshot=PYTEST_ITEM, skill="pytest", verdict="supported"
        )
        opened = await open_session(student, report_id, requirement_id)
        session_id = UUID(opened["id"])
        async with factory() as db:
            row = await db.get(InterviewSession, session_id)
            old = {**row.knowledge_snapshot[0], "contentHash": "legacy-hash"}
            old.pop("sourceUrl")
            row.knowledge_snapshot = [old]
            await db.commit()
        key = old["knowledgeId"]
        original = next(card for card in TECHNICAL_KNOWLEDGE if card["knowledge_id"] == key)
        route = f"/api/v1/interview-sessions/{session_id}"
        for field, value, stale in [
            ("tags", ["维护标签"], False),
            ("reviewed_at", "2026-11-11", False),
            ("summary", "只改摘要", False),
            ("source_url", "https://docs.pytest.org/en/stable/", False),
            ("source_locator", "新的具体章节", True),
            ("question_angles", ["仅修改出题角度"], True),
        ]:
            monkeypatch.setattr(
                technical_knowledge, "TECHNICAL_KNOWLEDGE", [{**original, field: value}]
            )
            async with factory() as db:
                assert await seed_technical_knowledge(db) == 1
                await db.commit()
                assert await seed_technical_knowledge(db) == 0
                card = await db.scalar(
                    select(TechnicalKnowledgeEntry).where(
                        TechnicalKnowledgeEntry.knowledge_id == key
                    )
                )
                assert getattr(card, field) == value
            current = (await student.get(route)).json()["data"]
            assert current["knowledgeOutdated"] is stale
        new = await student.post(
            f"/api/v1/match-reports/{report_id}/interview-sessions",
            json={"requirementId": requirement_id, "restart": True},
        )
        async with factory() as db:
            row = await db.get(InterviewSession, UUID(new.json()["data"]["session"]["id"]))
            assert row.knowledge_snapshot[0]["questionAngles"] == ["仅修改出题角度"]
            assert (await db.get(InterviewSession, session_id)).knowledge_snapshot == [old]


def test_legacy_consent_excludes_previous_turns_from_model_payload():
    service = practice.InterviewPracticeService(None)
    row = InterviewSession(max_turns=2, consent_scope="当前问题、你的回答")
    first = InterviewAnswer(
        turn_index=0,
        question_text="前轮问题",
        answer_text="前轮回答",
        feedback={"missing": ["前轮遗漏"]},
    )
    second = InterviewAnswer(turn_index=1, question_text="当前问题", answer_text="当前回答")
    legacy = service._feedback_data(row, second, [first])
    assert legacy["answer"] == "当前回答"
    assert legacy["previousTurns"] == legacy["previousIssues"] == []
    row.consent_scope = practice.CONSENT_SCOPE
    current = service._feedback_data(row, second, [first])
    assert current["previousTurns"] == [{"question": "前轮问题", "answer": "前轮回答"}]
    assert current["previousIssues"][0]["text"] == "前轮遗漏"


def test_summary_resolves_only_the_issue_supported_by_second_answer():
    first = InterviewAnswer(
        turn_index=0,
        answer_text="我会补充异常处理。",
        feedback={"missing": ["COUNT(*) 口径", "异常覆盖范围"]},
    )
    answer = "COUNT(*) 统计所有行，包括含 NULL 的行。"
    previous = practice._issue_records(first)
    raw = feedback(["正确说明行计数"], missing=["COUNT(*) 口径", "异常覆盖范围", "尚未给出样例"])
    raw["resolvedIssues"] = [{"issueId": previous[0]["issueId"], "answerQuote": answer}]
    options = dict(
        allowed_citations=set(),
        allowed_knowledge={"sql"},
        has_evidence=False,
        previous_issues=previous,
    )
    resolved = practice.validate_feedback(raw, answer=answer, **options)
    second = InterviewAnswer(turn_index=1, answer_text=answer, feedback=resolved)
    summary = practice.build_summary([first, second])
    assert summary["remaining"] == ["异常覆盖范围", "尚未给出样例"]
    assert summary["resolvedIssues"][0]["answerQuote"] == answer
    second.feedback = practice.validate_feedback(
        feedback(["只谈到改进计划"]), answer="我以后会补测试。", **options
    )
    assert practice.build_summary([first, second])["remaining"] == ["COUNT(*) 口径", "异常覆盖范围"]
    with pytest.raises(ValueError, match="引文"):
        practice.validate_feedback(raw, answer="我以后会补测试。", **options)
    raw["resolvedIssues"][0]["issueId"] = "2:missing:0"
    with pytest.raises(ValueError, match="不属于"):
        practice.validate_feedback(raw, answer=answer, **options)


def test_followup_groups_rephrased_issue_and_keeps_unrelated_issue():
    first = InterviewAnswer(
        turn_index=0, answer_text="COUNT(*) 统计行数。",
        feedback={"missing": ["未算出示例行数", "未说明 AVG 的分母", "未说明缺失偏差"]},
    )
    answer = "样例外连接保留三行，所以 COUNT(*) = 3。"
    raw = feedback(["算出三行"], missing=["还没说明 AVG 排除空值"])
    raw["findings"][1]["previousIssueId"] = "0:missing:1"
    raw["findings"][0]["previousIssueId"] = "0:missing:0"
    raw["resolvedIssues"] = [{"issueId": "0:missing:0", "answerQuote": answer}]
    options = dict(allowed_citations=set(), allowed_knowledge=set(), has_evidence=False,
                   answer=answer, previous_issues=practice._issue_records(first))
    second = InterviewAnswer(turn_index=1, answer_text=answer,
                             feedback=practice.validate_feedback(raw, **options))
    summary = practice.build_summary([first, second])
    assert summary["remaining"] == ["未说明缺失偏差", "还没说明 AVG 排除空值"]
    assert summary["resolvedIssues"][0]["text"] == "未算出示例行数"
    assert first.feedback["missing"][1] == "未说明 AVG 的分母"
    raw["findings"][1]["previousIssueId"] = "0:missing:0"
    with pytest.raises(ValueError, match="关联无效"):
        practice.validate_feedback(raw, **options)


def test_missing_requires_a_quote_from_the_actual_question():
    question_text = "说明 AVG(score) 的分母，并给出缺失偏差的数值例子。"
    options = dict(allowed_citations=set(), allowed_knowledge=set(), has_evidence=False,
                   answer="AVG 只用非空行数作分母。", previous_issues=[], question=question_text)
    raw = feedback(["解释了 AVG 分母"], missing=["没有说明缺失机制的定义"],
                   question_quote="缺失机制的定义")
    with pytest.raises(ValueError, match="遗漏项缺少本轮题目原文"):
        practice.validate_feedback(raw, **options)
    raw = feedback(["解释了 AVG 分母"], missing=["缺少缺失偏差的数值例子"],
                   question_quote="给出缺失偏差的数值例子")
    saved = practice.validate_feedback(raw, **options)
    assert saved["issueRecords"][0]["questionQuote"] == "给出缺失偏差的数值例子"


@pytest.mark.parametrize(
    ("answer", "raw", "expected"),
    [
        ("我会检查空值。", feedback(["提到空值"], missing=["未说明 COUNT(*)"]), "missing"),
        ("以后会补异常处理，旧代码尚未包含。", feedback(["区分了当前实现与计划"]), "covered"),
        (
            "可以用 COUNT(*) - COUNT(score) 统计缺失行。",
            feedback(["给出可行的替代统计办法"]),
            "covered",
        ),
        (
            "COUNT(*) 不计含 NULL 的行。",
            {
                **feedback([]),
                "findings": [
                    {
                        "point": "COUNT(*) 行数口径",
                        "kind": "inconsistent",
                        "text": "COUNT(*) 统计所有行。",
                        "answerQuote": "COUNT(*) 不计含 NULL 的行。",
                        "basisId": "sql",
                    }
                ],
            },
            "inconsistent",
        ),
    ],
)
def test_feedback_classification_contract(answer, raw, expected):
    saved = practice.validate_feedback(
        raw,
        answer=answer,
        previous_issues=[],
        allowed_knowledge={"sql"},
        allowed_citations=set(),
        has_evidence=False,
    )
    assert saved[expected]
    if expected != "inconsistent":
        assert not saved["inconsistent"]
    else:
        assert saved["conflictDetails"][0]["answerQuote"] == answer


def test_answered_incorrectly_cannot_also_be_missing_for_the_same_point():
    answer = "COUNT(*) 不统计含 NULL 的行"
    raw = feedback([])
    conflict = {
        "point": "COUNT(*) 行数口径",
        "kind": "inconsistent",
        "text": "COUNT(*) 统计结果行数，与列是否为 NULL 无关。",
        "answerQuote": answer,
        "basisId": "sql",
    }
    options = dict(
        answer=answer,
        previous_issues=[],
        allowed_knowledge={"sql"},
        allowed_citations=set(),
        has_evidence=False,
    )
    raw["findings"] = [
        conflict,
        {
            "point": "count(*)行数口径",
            "kind": "missing",
            "text": "未说明 COUNT(*) 回答的是结果行数这一统计口径",
        },
    ]
    with pytest.raises(ValueError, match="同一问点"):
        practice.validate_feedback(raw, **options)
    raw["findings"][1] = {
        "point": "缺失机制对均值的影响",
        "kind": "missing",
        "text": "未说明缺失机制对观测均值的影响。",
    }
    saved = practice.validate_feedback(raw, **options)
    assert saved["inconsistent"] == [conflict["text"]]
    assert saved["missing"] == [raw["findings"][1]["text"]]


def test_correct_off_topic_outer_join_count_is_not_a_sql_conflict():
    answer = "COUNT(*) 会计算外连接补出的行。"
    raw = feedback([])
    missing = {"point": "AVG 分母", "kind": "missing", "text": "未说明 AVG 对 NULL 的处理。"}
    raw["findings"] = [
        missing,
        {
            "point": "COUNT(*) 行数",
            "kind": "inconsistent",
            "text": "外连接补出的行也是结果行，会被 COUNT(*) 计入。",
            "answerQuote": answer,
            "basisId": "tech-sql-aggregate-null",
        },
    ]
    options = dict(
        answer=answer, previous_issues=[], allowed_knowledge={"tech-sql-aggregate-null"},
        allowed_citations=set(), has_evidence=False,
    )
    saved = practice.validate_feedback(raw, **options)
    assert saved["missing"] == [missing["text"]]
    assert saved["inconsistent"] == []

    raw["findings"] = raw["findings"][1:]
    with pytest.raises(practice.PracticeOutputError, match="没有可采用的问点"):
        practice.validate_feedback(raw, **options)

    wrong = "COUNT(*) 不统计含 NULL 的行。"
    raw["findings"][0].update(
        answerQuote=wrong, text="COUNT(*) 统计结果行数，包括含 NULL 的行。"
    )
    saved = practice.validate_feedback(raw, **{**options, "answer": wrong})
    assert saved["conflictDetails"][0]["answerQuote"] == wrong


async def test_slow_feedback_duplicate_retry_and_late_result(practice_db, monkeypatch):
    app, factory = practice_db
    async with await client_for(app) as student:
        user = await register(student, "practice-slow@example.com", "student")
        report_id, requirement_id, _ = await seed(
            factory, user["id"], item_snapshot=PYTEST_ITEM, skill="pytest", verdict="supported"
        )
        entered, release = asyncio.Event(), asyncio.Event()
        provider = use_provider(
            monkeypatch,
            [question("这条测试覆盖什么情况？"), feedback(["旧迟到点评"]), feedback(["新点评"])],
        )
        original = provider.generate_bounded_json

        async def slow(**kwargs):
            response = await original(**kwargs)
            if len(provider.calls) == 2:
                entered.set()
                await release.wait()
            return response

        monkeypatch.setattr(provider, "generate_bounded_json", slow)
        opened = await open_session(student, report_id, requirement_id)
        route = f"/api/v1/interview-sessions/{opened['id']}"
        first = await student.post(f"{route}/start", json={"externalAiConsent": True})
        assert first.json()["data"]["questionTask"]["status"] == "pending"
        await dispatch_pending_tasks(factory)
        await wait_for_dispatched_tasks()
        payload = {"answerText": "只覆盖正常输入。", "clientToken": "token-slow"}
        submitted, duplicate = await asyncio.gather(
            *[student.post(f"{route}/turns/0/answers", json=payload) for _ in range(2)]
        )
        task = submitted.json()["data"]["turns"][0]["feedbackTask"]
        assert duplicate.json()["data"]["turns"][0]["feedbackTask"]["id"] == task["id"]
        assert task["status"] == "pending"
        task_id = UUID(task["id"])
        running = asyncio.create_task(practice.execute_interview_task(task_id, factory))
        await asyncio.wait_for(entered.wait(), timeout=3)
        try:
            assert await dispatch_pending_tasks(factory) == 0
            retry = await student.post(f"{route}/turns/0/retry")
            assert retry.json()["data"]["turns"][0]["feedbackTask"] == {**task, "status": "running"}
            assert len(provider.calls) == 2
            async with factory() as db:
                await db.execute(
                    update(AnalysisTask)
                    .where(AnalysisTask.id == task_id)
                    .values(heartbeat_at=datetime.now(UTC) - timedelta(days=1))
                )
                await db.commit()
            assert await recover_interrupted_tasks(factory) == 1
            read = (await student.get(route)).json()["data"]["turns"][0]
            assert read["state"] == "failed" and read["answerText"] == payload["answerText"]
            assert "上传" not in read["failureReason"]
            retry = await student.post(f"{route}/turns/0/retry")
            assert retry.json()["data"]["turns"][0]["feedbackTask"]["id"] == task["id"]
            await dispatch_pending_tasks(factory)
            # The late response can finish while the replacement lease owns the task.
            release.set()
            await wait_for_dispatched_tasks()
        finally:
            release.set()
            await running
        saved = (await student.get(route)).json()["data"]
        assert saved["currentTurn"] == 1 and len(saved["turns"]) == 2
        assert saved["turns"][0]["feedback"]["covered"] == ["新点评"]
        async with factory() as db:
            assert (await db.get(AnalysisTask, task_id)).attempt == 2
            usage = list(
                await db.scalars(select(AiUsageLog).where(AiUsageLog.analysis_task_id == task_id))
            )
            assert len({entry.run_token for entry in usage}) == len(usage) == 2

def test_summary_keeps_unresolved_issues_from_both_turns():
    turns = [
        InterviewAnswer(
            turn_index=index,
            answer_text="已保存回答",
            feedback={
                "missing": [f"第{index + 1}轮遗漏{i}" for i in range(4)],
                "inconsistent": [f"第{index + 1}轮需修正{i}" for i in range(4)],
            },
        )
        for index in range(2)
    ]
    summary = practice.build_summary(turns)
    assert len(summary["remaining"]) == 8
    assert summary["remaining"][-1] == "第2轮遗漏3"
    assert len(summary["inconsistent"]) == 8
    assert summary["inconsistent"][-1] == "第2轮需修正3"

async def test_interview_index_is_paginated_private_and_read_only(practice_db, monkeypatch):
    app, factory = practice_db
    owner = await client_for(app)
    other = await client_for(app)
    company = await client_for(app)
    user = await register(owner, "practice-index-owner@example.com", "student")
    foreign = await register(other, "practice-index-other@example.com", "student")
    await register(company, "practice-index-company@example.com", "enterprise")
    provider = use_provider(monkeypatch, [])
    endpoint = "/api/v1/interview-sessions"

    empty = await owner.get(endpoint)
    assert empty.status_code == 200
    assert empty.json()["data"]["total"] == 0
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=SQL_ITEM, skill="SQL", verdict="supported"
    )
    first = await open_session(owner, report_id, requirement_id)
    second = await owner.post(
        f"/api/v1/match-reports/{report_id}/interview-sessions",
        json={"requirementId": requirement_id, "restart": True},
    )
    assert second.status_code == 200
    second_id = second.json()["data"]["session"]["id"]
    assert second_id != first["id"]

    for page_number, expected in [(1, second_id), (2, first["id"])]:
        response = await owner.get(endpoint, params={"page": page_number, "pageSize": 1})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 2
        assert data["page"] == page_number
        row, = data["items"]
        assert row["id"] == expected
        assert row["status"] == "draft"
        assert row["requirementTitle"] == SQL_ITEM["requirementTitle"]
        assert set(row) == {
            "id", "jobId", "jobTitle", "requirementTitle", "skill",
            "status", "needsAttention", "updatedAt",
        }
    assert (await owner.get(endpoint, params={"pageSize": 51})).status_code == 422
    assert (await other.get(endpoint)).json()["data"]["total"] == 0
    assert (await company.get(endpoint)).status_code == 403
    assert (await other.get(f"{endpoint}/{first['id']}")).status_code == 404

    async with factory() as session:
        report = await session.get(MatchReport, UUID(report_id))
        report.candidate_ref = foreign["id"]
        await session.commit()
    assert (await owner.get(endpoint)).json()["data"]["total"] == 0
    assert provider.calls == []
