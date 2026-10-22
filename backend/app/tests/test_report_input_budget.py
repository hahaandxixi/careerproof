import json
from pathlib import Path

import httpx
import pytest

from app.agents.contracts import RequirementEvidenceContext
from app.agents.evidence_workflow import build_evidence_contexts, run_evidence_workflow
from app.agents.provider import (
    ProviderInputBudgetError,
    ProviderOutputBudgetError,
    evidence_analysis_messages,
    sanitize_outgoing_messages,
)
from app.core.config import settings
from app.tests.test_ai_evidence_workflow import evidenced_result
from app.tests.test_deepseek_provider import provider


def answer(context):
    citation = context.evidence[0].citation_id
    return {
        "summary": "材料包含路由声明及空函数，运行结果待核验。",
        "items": [{
            "requirement_id": context.requirement_id,
            "explanation": "材料含路由声明，函数为空实现。",
            "citation_ids": [citation],
            "information_gap": "运行结果与本人贡献待核验。",
            "suggestion": "补充实际实现与运行记录。",
            "confidence": 0.5,
            "rating": {
                "level": 1,
                "reason": "仅展示相关线索。",
                "criteria": [
                    {"criterion": "relevance", "supported": True,
                     "citation_ids": [citation], "reason": "材料展示相关路由声明。"},
                    {"criterion": "operation", "supported": False,
                     "citation_ids": [], "reason": "函数为空实现。"},
                    {"criterion": "task", "supported": False,
                     "citation_ids": [], "reason": "未展示完整任务。"},
                ],
            },
        }],
    }


def response(context):
    return httpx.Response(200, json={
        "model": "deepseek-flash",
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(answer(context), ensure_ascii=False),
        }}],
        "usage": {"prompt_tokens": 80, "completion_tokens": 40},
    })


def enable(monkeypatch, instance, limit):
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr(settings, "ai_max_retrieval_calls", 2)
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", limit)
    monkeypatch.setattr(settings, "ai_per_report_output_token_limit", 4000)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: instance)


@pytest.mark.asyncio
async def test_final_report_reservation_skips_planning_without_fake_tool_event(monkeypatch):
    result = evidenced_result()
    context = build_evidence_contexts(result, max_evidence=2)[0]
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert "tools" not in body
        return response(context)

    instance = provider(transport=httpx.MockTransport(handler))
    required = instance.estimate_evidence_input([context])
    enable(monkeypatch, instance, required)
    notices = []

    async def notify(message):
        notices.append(message)

    outcome = await run_evidence_workflow(result, notify)
    assert not outcome.fallback_used and outcome.analysis is not None
    assert len(calls) == outcome.request_count == 1
    assert outcome.tool_calls == ()
    assert outcome.planning_skipped_reason == "report_budget_reserved"
    assert any("预留" in notice for notice in notices)
    assert outcome.analysis.usage.input_tokens == 80
    assert outcome.provider_finish_reason == "stop"


@pytest.mark.asyncio
async def test_history_growth_keeps_final_input_and_actual_usage(monkeypatch):
    result = evidenced_result()
    context = build_evidence_contexts(result, max_evidence=2)[0]
    history = {"previousReportId": "synthetic", "explanation": "仅为历史参考。" * 500}
    calls, reads = [], []
    instance = None

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if "tools" in body:
            assert len(calls) == 1, "Second planning call must be locally blocked"
            return httpx.Response(200, json={
                "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{
                    "function": {"name": "get_previous_report_context", "arguments": json.dumps({
                        "requirement_id": context.requirement_id,
                    })},
                }]}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            })
        expected = sanitize_outgoing_messages(
            evidence_analysis_messages([context], history_context=history)
        )
        assert body["messages"] == expected
        return response(context)

    instance = provider(transport=httpx.MockTransport(handler))
    instance.history_context = history
    final_required = instance.estimate_evidence_input([context])
    del instance.history_context
    enable(monkeypatch, instance, final_required + 100 + 250)

    async def load_history(requirement_id):
        reads.append(requirement_id)
        return history

    outcome = await run_evidence_workflow(result, history_loader=load_history)
    assert not outcome.fallback_used and outcome.analysis is not None
    assert reads == [context.requirement_id]
    assert len(calls) == 2
    assert outcome.planning_skipped_reason == "report_budget_reserved"
    assert len(outcome.tool_calls) == 1
    assert outcome.tool_calls[0]["tool"] == "get_previous_report_context"
    assert outcome.tool_calls[0]["status"] == "completed"
    assert outcome.analysis.usage.input_tokens == 180
    assert outcome.analysis.usage.output_tokens == 50
    assert len(instance.request_usages) == 2
    assert outcome.provider_finish_reason == "stop"


@pytest.mark.asyncio
async def test_final_input_limit_is_not_a_provider_fault_and_never_sends(monkeypatch):
    def forbidden(_request):
        pytest.fail("No external request permitted for an oversized prompt")

    result = evidenced_result()
    instance = provider(transport=httpx.MockTransport(forbidden))
    instance.last_finish_reason = "tool_calls"
    required = instance.estimate_evidence_input(build_evidence_contexts(result, max_evidence=2))
    enable(monkeypatch, instance, required - 1)
    outcome = await run_evidence_workflow(result)
    assert outcome.fallback_used and outcome.analysis is None
    assert outcome.fallback_reason == "input_token_limit"
    assert outcome.failure_stage == "request"
    assert outcome.tool_calls == ()
    assert outcome.attempted_usage is None
    assert outcome.provider_finish_reason is None
    assert instance.request_usages == []
    assert outcome.input_budget_stop == {
        "estimatedInputBound": required,
        "remainingInputBudget": required - 1,
        "estimateMethod": "utf8-wire-bytes-plus-safety-margin",
    }


@pytest.mark.asyncio
async def test_repair_budget_diagnostics_keep_first_response_usage(monkeypatch):
    result = evidenced_result()
    context = build_evidence_contexts(result, max_evidence=2)[0]
    calls = []

    def handler(request):
        calls.append(request)
        payload = response(context).json()
        rejected = answer(context)
        rejected["items"][0]["citation_ids"] = ["R1-E99"]
        payload["choices"][0]["message"]["content"] = json.dumps(rejected, ensure_ascii=False)
        return httpx.Response(200, json=payload)

    instance = provider(transport=httpx.MockTransport(handler))
    required = instance.estimate_evidence_input([context])
    limit = required + 100
    enable(monkeypatch, instance, limit)
    monkeypatch.setattr(settings, "ai_max_retrieval_calls", 0)
    outcome = await run_evidence_workflow(result)
    assert outcome.fallback_used and outcome.analysis is None
    assert outcome.fallback_reason == "input_token_limit"
    assert outcome.failure_stage == "repair"
    assert len(calls) == 1
    assert outcome.request_count == 2
    assert outcome.attempted_usage.input_tokens == 80
    assert outcome.attempted_usage.output_tokens == 40
    assert outcome.input_budget_stop["remainingInputBudget"] == limit - 80
    assert outcome.input_budget_stop["estimatedInputBound"] > limit - 80
    assert outcome.input_budget_stop["estimateMethod"] == "utf8-wire-bytes-plus-safety-margin"
    assert len(outcome.input_preflights) == 2
    assert outcome.input_preflights[0]["allowed"] is True
    assert outcome.input_preflights[1]["allowed"] is False
    assert set(outcome.input_preflights[1]) == {
        "requestKind", "estimatedInputBound", "remainingInputBudget", "estimateMethod",
        "safetyMarginBytes", "allowed",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["analyze_evidence", "plan_evidence_retrieval"])
@pytest.mark.parametrize("limit,exception", [
    ({"input_token_limit": 0}, ProviderInputBudgetError),
    ({"input_token_limit": -1}, ProviderInputBudgetError),
    ({"output_token_limit": 0}, ProviderOutputBudgetError),
    ({"output_token_limit": -1}, ProviderOutputBudgetError),
])
async def test_explicit_empty_limits_do_not_restore_default_budget(method, limit, exception):
    instance = provider(transport=httpx.MockTransport(lambda _: pytest.fail("No network")))
    instance.last_finish_reason = "tool_calls"
    with pytest.raises(exception):
        await getattr(instance, method)(
            contexts=build_evidence_contexts(evidenced_result()), **limit
        )
    assert instance.request_usages == []
    assert instance.last_finish_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize("requirement_count", [1, 5])
async def test_default_budget_admits_complete_minimum_and_typical_request(
    monkeypatch, requirement_count,
):
    """Default admission includes policy, rubric, evidence and complete wire shape."""
    default_limit = type(settings).model_fields["ai_per_report_input_token_limit"].default
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", default_limit)
    original = build_evidence_contexts(evidenced_result())[0]
    contexts = [
        original.model_copy(update={"requirement_id": str(index)})
        for index in range(requirement_count)
    ]
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        payload = response(contexts[0]).json()
        content = answer(contexts[0])
        content["items"] = [answer(context)["items"][0] for context in contexts]
        payload["choices"][0]["message"]["content"] = json.dumps(content, ensure_ascii=False)
        return httpx.Response(200, json=payload)

    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    analysis = await instance.analyze_evidence(contexts=contexts)
    assert len(sent) == 1
    assert len(analysis.items) == requirement_count
    assert instance.input_preflights[0]["allowed"] is True
    assert instance.input_preflights[0]["estimatedInputBound"] <= default_limit
    assert analysis.usage.input_tokens == 80  # Provider receipt, not byte estimate.
    print({"requirements": requirement_count, "limit": default_limit,
           "preflight": instance.input_preflights[0]})


@pytest.mark.asyncio
async def test_default_workflow_reserves_final_request_before_mock_planning(monkeypatch):
    result = evidenced_result()
    context = build_evidence_contexts(result, max_evidence=2)[0]
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if "tools" in body:
            return httpx.Response(200, json={
                "choices": [{"finish_reason": "stop", "message": {"content": "stop"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            })
        return response(context)

    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    limit = type(settings).model_fields["ai_per_report_input_token_limit"].default
    enable(monkeypatch, instance, limit)
    outcome = await run_evidence_workflow(result)
    assert not outcome.fallback_used
    assert outcome.analysis is not None
    assert len(calls) == 2
    assert "tools" in calls[0] and "tools" not in calls[1]
    assert outcome.analysis.usage.input_tokens == 180
    assert outcome.analysis.usage.output_tokens == 50
    assert outcome.tool_calls[0]["reason"] == "planner_declined"
    assert all(entry["allowed"] for entry in outcome.input_preflights)


@pytest.mark.asyncio
async def test_default_budget_admits_frozen_complete_project_request(monkeypatch):
    """Admission only: fixed real synthetic project, never a semantic model verdict."""
    fixture = json.loads(
        Path(__file__).with_name("fixtures").joinpath(
            "complete-project-budget-contexts.json"
        ).read_text(encoding="utf-8")
    )
    assert fixture["syntheticOnly"] is True
    contexts = [RequirementEvidenceContext.model_validate(row) for row in fixture["contexts"]]
    assert len(contexts) == 5
    assert len({e.file_path for c in contexts for e in c.evidence}) >= 5
    default_limit = type(settings).model_fields["ai_per_report_input_token_limit"].default
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", default_limit)
    requests = []

    def handler(request):
        requests.append(request)
        payload = response(contexts[0]).json()
        content = answer(contexts[0])
        content["items"] = [answer(context)["items"][0] for context in contexts]
        payload["choices"][0]["message"]["content"] = json.dumps(content, ensure_ascii=False)
        return httpx.Response(200, json=payload)

    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    await instance.analyze_evidence(contexts=contexts)
    assert len(requests) == 1
    assert instance.input_preflights[0]["allowed"] is True
    assert instance.input_preflights[0]["estimatedInputBound"] <= default_limit
    print({"completeProjectRequirements": 5, "limit": default_limit,
           "preflight": instance.input_preflights[0]})
