"""Interview practice: one requirement, fixed citations, no duplicate model calls.

All model traffic is a local stub. No test reads a real provider or writes a
report verdict, growth draft or application.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.knowledge.technical_seed import TECHNICAL_KNOWLEDGE, content_digest
from app.models.analysis import AiUsageLog, AnalysisTask, MatchItem, MatchReport
from app.models.enums import TaskStatus
from app.models.growth_answer import GrowthAnswerDraft
from app.models.identity import StudentProfile
from app.models.knowledge import TechnicalKnowledgeEntry
from app.models.portfolio import InterviewAnswer, InterviewSession
from app.models.recruitment import Job, JobRequirement
from app.services import interview_practice as practice
from app.services.technical_knowledge import seed_technical_knowledge
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
    "requirementTitle": "使用 SQL 核查异常结果",
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
):
    return {
        "covered": list(covered),
        "inconsistent": [],
        "missing": list(missing),
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


async def client_for(app):
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
    student = await client_for(app)
    user = await register(student, "practice-a@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=PYTEST_ITEM, skill="pytest", verdict="supported"
    )

    async with factory() as session:
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
    student = await client_for(app)
    user = await register(student, "practice-sql@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=SQL_ITEM, skill="SQL", verdict="claimed_only"
    )
    async with factory() as session:
        knowledge_id = await session.scalar(
            select(TechnicalKnowledgeEntry.knowledge_id).where(
                TechnicalKnowledgeEntry.skill == "SQL"
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
    assert rejected.status_code == 503
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
    student = await client_for(app)
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


async def test_ai_failure_keeps_answer_and_retry_completes(practice_db, monkeypatch):
    app, factory = practice_db
    student = await client_for(app)
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
            TimeoutError(),
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
    assert "超时" in turn["failureReason"]

    read = await student.get(f"/api/v1/interview-sessions/{opened['id']}")
    assert read.json()["data"]["turns"][0]["answerText"] == "只覆盖了正常输入。"

    retried = await student.post(f"/api/v1/interview-sessions/{opened['id']}/turns/0/retry")
    assert retried.status_code == 200
    assert retried.json()["data"]["turns"][0]["state"] == "feedback"


async def test_other_student_cannot_read_or_continue(practice_db, monkeypatch):
    app, factory = practice_db
    owner = await client_for(app)
    stranger = await client_for(app)
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
    student = await client_for(app)
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
    student = await client_for(app)
    user = await register(student, "practice-sql-aggregate@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=SQL_ITEM, skill="SQL", verdict="claimed_only"
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
    student = await client_for(app)
    user = await register(student, "practice-sql-stale@example.com", "student")
    report_id, requirement_id, _ = await seed(
        factory, user["id"], item_snapshot=SQL_ITEM, skill="SQL", verdict="claimed_only"
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

