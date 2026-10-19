import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.evidence_workflow import run_evidence_workflow
from app.agents.provider import DeepSeekProvider, evidence_analysis_messages
from app.core.config import settings
from app.models.analysis import AnalysisTask, MatchItem, MatchReport
from app.services.analysis import _analysis_cache_key
from app.services.report_history import prepare_history_tool
from app.tests.test_ai_evidence_workflow import evidenced_result
from app.tests.test_jobs_api import job_payload, jobs_db, organization, register  # noqa: F401


async def test_history_query_excludes_other_owner_and_future_report(jobs_db):  # noqa: F811
    app, factory = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        owner = await register(client, "history-owner@example.com")
        org = await organization(client)
        job = (await client.post("/api/v1/jobs", json=job_payload(org))).json()["data"]
        requirement_id = job["requirements"][0]["id"]
        other = await register(client, "history-other@example.com", "student")
        now = datetime.now(UTC)
        async with factory() as session:
            report_ids = []
            for user_id, offset, explanation in (
                (owner["id"], -2, "旧判断可能错误 R1-E1"),
                (other["id"], -1, "其他用户私有说明"),
                (owner["id"], 1, "未来报告"),
            ):
                task = AnalysisTask(created_by=UUID(user_id), task_type="job_match")
                session.add(task)
                await session.flush()
                report = MatchReport(
                    analysis_task_id=task.id,
                    job_id=UUID(job["id"]),
                    candidate_ref=owner["id"],
                    summary="合成历史",
                    created_at=now + timedelta(days=offset),
                    job_snapshot={
                        "requirements": [{"id": requirement_id, "title": "旧要求 R8-E1"}]
                    },
                )
                session.add(report)
                await session.flush()
                report_ids.append(str(report.id))
                session.add(
                    MatchItem(
                        report_id=report.id,
                        requirement_id=UUID(requirement_id),
                        rule_base_score=1,
                        weight=3,
                        verdict="supported",
                        explanation=explanation,
                        formula_version="old",
                        evidence_snapshot={
                            "ai": {"explanation": explanation, "rating": {"level": 3}},
                            "evidenceList": [
                                {
                                    "citationId": "R1-E1",
                                    "filePath": "R4-E2/old.py",
                                    "lineStart": 2,
                                    "lineEnd": 5,
                                    "contentHash": "a" * 64,
                                    "snippet": "old code R1-E1",
                                }
                            ],
                        },
                    )
                )
            await session.commit()
            current = SimpleNamespace(
                created_by=UUID(owner["id"]), created_at=now, input_snapshot={"jobId": job["id"]}
            )
            read = await prepare_history_tool(
                session, current, [{"id": requirement_id, "title": "新要求"}],
                session_factory=factory,
            )
            result = await read(requirement_id)
            assert result["requirementChanged"] is True
            assert result["savedAiLevel"] == 3
            assert result["previousItemAvailable"] is True
            assert result["previousEvidence"][0]["lineStart"] == 2
            assert result["previousEvidence"][0]["contentHash"] == "a" * 64
            assert "旧判断" in result["previousExplanation"]
            assert "R1-E1" not in json.dumps(result)
            assert "R8-E1" not in json.dumps(result) and "R4-E2" not in json.dumps(result)
            assert "其他用户" not in json.dumps(result) and "未来报告" not in json.dumps(result)
            with pytest.raises(ValueError, match="unknown current requirement"):
                await read("unknown")
            # An explicitly frozen empty history cannot drift to a later report.
            current.input_snapshot["previousReportId"] = None
            assert await prepare_history_tool(
                session, current, [{"id": requirement_id}], session_factory=factory
            ) is None
            # Even a forged pinned report must obey owner and before-task constraints.
            for invalid_id in report_ids[1:]:
                current.input_snapshot["previousReportId"] = invalid_id
                denied = await prepare_history_tool(
                    session, current, [{"id": requirement_id}], session_factory=factory
                )
                assert denied is None
            current.input_snapshot["previousReportId"] = report_ids[0]
            frozen = await prepare_history_tool(
                session, current, [{"id": requirement_id}], session_factory=factory
            )
            assert (await frozen(requirement_id))["previousReportId"] == report_ids[0]
            new_requirement_id = str(uuid4())
            added = await prepare_history_tool(
                session, current, [{"id": new_requirement_id}], session_factory=factory
            )
            missing_item = await added(new_requirement_id)
            assert missing_item["previousItemAvailable"] is False
            assert missing_item["requirementChanged"] is True
            assert missing_item["previousRequirement"] is None
            assert missing_item["savedAiLevel"] is None and not missing_item["previousEvidence"]


def test_cache_key_separates_history_consent_and_frozen_source():
    snapshot = {"job": {}, "materials": [], "externalAiConsent": True}
    ordinary = _analysis_cache_key(snapshot)
    opted = _analysis_cache_key({**snapshot, "usePreviousReport": True})
    pinned = _analysis_cache_key(
        {**snapshot, "usePreviousReport": True, "previousReportId": "synthetic-first"}
    )
    changed = _analysis_cache_key(
        {**snapshot, "usePreviousReport": True, "previousReportId": "synthetic-second"}
    )
    assert len({ordinary, opted, pinned, changed}) == 4


def test_cache_key_separates_saved_rule_interpretation_profiles(monkeypatch):
    from app.services import analysis

    snapshot = {"job": {}, "materials": [], "externalAiConsent": False}
    monkeypatch.setattr(
        analysis, "EVIDENCE_LEVEL_VERSION", "practice-evidence-v4-candidate-boundary"
    )
    previous = analysis._analysis_cache_key(snapshot)
    monkeypatch.setattr(analysis, "EVIDENCE_LEVEL_VERSION", "practice-evidence-v5-redis-operation")
    assert analysis._analysis_cache_key(snapshot) != previous


@pytest.mark.parametrize("history_fault", [False, True])
@pytest.mark.parametrize("response_fault", [None, "historical_citation", "old_level"])
async def test_model_selects_history_once_without_promoting_old_level(
    monkeypatch, history_fault, response_fault
):
    result = evidenced_result()
    requirement_id = str(result.items[0].requirement_id)
    seen = []
    reads = []

    async def read(target):
        reads.append(target)
        if history_fault:
            raise ValueError("Synthetic optional-history failure")
        return {
            "savedAiLevel": 3,
            "previousExplanation": "old@example.com 13800138000",
            "previousEvidence": [{"historicalReference": "history-1", "snippet": "old code"}],
        }

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if "tools" in body:
            if "get_previous_report_context" not in [t["function"]["name"] for t in body["tools"]]:
                return httpx.Response(
                    200, json={"choices": [{"message": {"content": "无需补检索"}}]}
                )
            message = {
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_previous_report_context",
                            "arguments": json.dumps({"requirement_id": requirement_id}),
                        }
                    }
                ]
            }
        else:
            assert "old@example.com" not in body["messages"][1]["content"]
            assert "13800138000" not in body["messages"][1]["content"]
            answer = {
                "summary": "当前材料只展示路由线索。",
                "items": [
                    {
                        "requirement_id": requirement_id,
                        "explanation": "当前片段含路由声明和空函数。",
                        "citation_ids": ["R1-E1"],
                        "information_gap": "运行结果与本人贡献未核验。",
                        "suggestion": "补充处理代码和运行记录。",
                        "confidence": 0.5,
                        "rating": {
                            "level": 1,
                            "reason": "只有相关线索。",
                            "criteria": [
                                {
                                    "criterion": "relevance",
                                    "supported": True,
                                    "citation_ids": ["R1-E1"],
                                    "reason": "路由声明可见。",
                                },
                                {
                                    "criterion": "operation",
                                    "supported": False,
                                    "citation_ids": [],
                                    "reason": "函数体为空。",
                                },
                                {
                                    "criterion": "task",
                                    "supported": False,
                                    "citation_ids": [],
                                    "reason": "没有完整任务实现。",
                                },
                            ],
                        },
                    }
                ],
            }
            if response_fault == "historical_citation":
                answer["items"][0]["citation_ids"] = ["history-1"]
            elif response_fault == "old_level":
                answer["items"][0]["rating"]["level"] = 3
            message = {"content": json.dumps(answer, ensure_ascii=False)}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": message}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100},
            },
        )

    provider = DeepSeekProvider(
        api_key="synthetic-key",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: provider)
    outcome = await run_evidence_workflow(result, history_loader=read)
    assert reads == [requirement_id]
    if response_fault:
        assert outcome.fallback_used and outcome.analysis is None
        assert outcome.failure_stage == "repair"
        assert sum("tools" not in request for request in seen) == 2
        assert outcome.contexts[0].rating_ceiling < 3
    else:
        assert not outcome.fallback_used
        assert outcome.analysis.items[0].rating.level == 1
    assert any(
        event["tool"] == "get_previous_report_context"
        and event["status"] == ("unavailable" if history_fault else "completed")
        for event in outcome.tool_calls
    )
    assert len(seen) <= 4


@pytest.mark.asyncio
async def test_ineligible_second_retrieval_is_rejected_without_losing_analysis(monkeypatch):
    result = evidenced_result()
    first = result.items[0].evidence_list[0]
    full_item = replace(
        result.items[0],
        evidence_list=[
            first,
            replace(
                first,
                file_path="routes.py",
                line_start=8,
                line_end=10,
                snippet="@app.get('/items')\ndef items():\n    return []",
                content_hash="3" * 64,
            ),
            replace(
                first,
                file_path="service.py",
                line_start=2,
                line_end=4,
                snippet="def service():\n    return {'ok': True}",
                content_hash="4" * 64,
            ),
        ],
    )
    result = replace(
        result,
        items=[
            full_item,
            replace(
                full_item,
                requirement_id=uuid4(),
                requirement_title="有 Redis 缓存实践",
                skill="Redis",
                weight=3,
            ),
        ],
    )
    requirement_id = str(result.items[0].requirement_id)
    other_requirement_id = str(result.items[1].requirement_id)
    planning_requests = []

    def handler(request):
        body = json.loads(request.content)
        if "tools" in body:
            planning_requests.append(body)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "retrieve_more_evidence",
                                            "arguments": json.dumps(
                                                {
                                                    "requirement_id": requirement_id,
                                                    "query": "完整路由与返回实现",
                                                }
                                            ),
                                        }
                                    }
                                ]
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 10},
                },
            )
        def analysis_item(target, citation, reason):
            return {
                "requirement_id": target,
                "explanation": "片段包含实现线索，运行结果仍待核验。",
                "citation_ids": [citation],
                "information_gap": "运行结果与本人贡献仍待核验。",
                "suggestion": "补充运行记录。",
                "confidence": 0.5,
                "rating": {
                    "level": 1,
                    "reason": "只确认相关实现线索。",
                    "criteria": [
                        {
                            "criterion": "relevance",
                            "supported": True,
                            "citation_ids": [citation],
                            "reason": reason,
                        },
                        {
                            "criterion": "operation",
                            "supported": False,
                            "citation_ids": [],
                            "reason": "未展示完整运行结果。",
                        },
                        {
                            "criterion": "task",
                            "supported": False,
                            "citation_ids": [],
                            "reason": "未展示完整任务实现。",
                        },
                    ],
                },
            }

        answer = {
            "summary": "当前材料展示实现片段。",
            "items": [
                analysis_item(requirement_id, "R1-E3", "片段含 FastAPI 路由声明。"),
                analysis_item(other_requirement_id, "R2-E1", "片段含 Redis 相关线索。"),
            ],
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100},
            },
        )

    async def read(_requirement_id):
        return {"savedAiLevel": 1, "previousExplanation": "旧解释", "previousEvidence": []}

    provider = DeepSeekProvider(
        api_key="synthetic-key",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
        max_attempts=1,
    )
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr(settings, "ai_max_retrieval_calls", 2)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: provider)

    outcome = await run_evidence_workflow(result, history_loader=read)

    assert len(planning_requests) == 2
    assert not outcome.fallback_used and outcome.analysis is not None
    assert outcome.analysis.items[0].citation_ids == ["R1-E3"]
    assert outcome.tool_calls[0]["resultCount"] == 1
    assert outcome.tool_calls[0]["status"] == "completed"
    assert outcome.tool_calls[-1]["status"] == "rejected"
    assert outcome.tool_calls[-1]["reason"] == "ineligible_retrieval_scope"


def test_historical_context_has_separate_prompt_boundary():
    messages = evidence_analysis_messages([], history_context={"savedAiLevel": 3})
    assert "不能支持当前评级" in messages[0]["content"]
    assert "historicalContext" in messages[1]["content"]
