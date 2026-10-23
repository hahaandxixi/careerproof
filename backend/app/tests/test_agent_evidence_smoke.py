import asyncio
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.provider import EVIDENCE_PROMPT_VERSION, DeepSeekProvider
from app.core.config import settings
from evals import bounded_evidence_smoke as smoke


def packet_path() -> Path:
    # Current-source offline regression input is separate from immutable live preflights.
    return Path(__file__).parent / "fixtures/current-20261022/agent-offline-input.json"


def packet() -> dict:
    return json.loads(packet_path().read_text(encoding="utf-8"))


def test_current_offline_packet_keeps_historical_cases_without_reauthorizing_them():
    data = packet()
    historical = smoke.ROOT / data["historicalPacket"]["path"]
    assert data["offlineOnly"] is True
    assert data["promptVersion"] == EVIDENCE_PROMPT_VERSION
    assert hashlib.sha256(historical.read_bytes()).hexdigest() == data["historicalPacket"]["sha256"]
    original = json.loads(historical.read_text(encoding="utf-8"))
    assert data["cases"] == original["cases"]
    assert data["limits"] == original["limits"]
    assert set(data["sourceHashes"]) == {
        *original["sourceHashes"],
        "backend/app/agents/evidence_policy.md",
        "backend/app/agents/input_budget.py",
    }
    smoke.check_agent_packet(data)


@pytest.mark.parametrize("relative", [
    "backend/app/agents/evidence_policy.md",
    "backend/app/agents/input_budget.py",
])
def test_reviewed_policy_and_budget_content_mutation_is_rejected(monkeypatch, tmp_path, relative):
    data = packet()
    source = (smoke.ROOT / relative).read_bytes()
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(source)
    data["sourceHashes"] = {relative: data["sourceHashes"][relative]}
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    smoke.check_agent_packet(data)
    target.write_bytes(source + b"\n# actual content mutation\n")
    with pytest.raises(smoke.SmokeStopped, match="source changed"):
        smoke.check_agent_packet(data)


def test_historical_agent_packet_is_rejected_after_reviewed_source_changes():
    historical = smoke.ROOT / packet()["historicalPacket"]["path"]
    with pytest.raises(smoke.SmokeStopped, match="source changed"):
        smoke.check_agent_packet(json.loads(historical.read_text(encoding="utf-8")))


def planning_request() -> dict:
    return {
        "model": "deepseek-flash",
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": "synthetic"}],
        "max_tokens": 1200,
        "tool_choice": "auto",
        "tools": [
            {
                "type": "function",
                "function": {"name": "retrieve_more_evidence", "parameters": {"type": "object"}},
            }
        ],
    }


def analysis_request() -> dict:
    return {
        "model": "deepseek-flash",
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": "synthetic analysis"}],
        "max_tokens": 1200,
    }


def answer(case: dict, citation: str) -> dict:
    return {
        "summary": "合成材料只展示代码线索，不能证明运行或录用。",
        "items": [
            {
                "requirement_id": case["requirementId"],
                "explanation": "引用只支持存在相关实现线索，运行与贡献仍待核验。",
                "citation_ids": [citation],
                "information_gap": "运行结果、测试执行与本人贡献未证明。",
                "suggestion": "补充可定位的运行记录并说明本人负责部分。",
                "confidence": 0.5,
                "rating": {
                    "level": 1,
                    "reason": "仅有相关实现线索。",
                    "criteria": [
                        {
                            "criterion": "relevance",
                            "supported": True,
                            "citation_ids": [citation],
                            "reason": "引用相关。",
                        },
                        {
                            "criterion": "operation",
                            "supported": False,
                            "citation_ids": [],
                            "reason": "未展示运行。",
                        },
                        {
                            "criterion": "task",
                            "supported": False,
                            "citation_ids": [],
                            "reason": "未展示完整任务。",
                        },
                    ],
                },
            }
        ],
    }


def tool_response(name: str, case: dict) -> httpx.Response:
    arguments = {"requirement_id": case["requirementId"]}
    if name == "retrieve_more_evidence":
        arguments["query"] = "rollback"
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(arguments),
                                }
                            }
                        ]
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
        },
    )


def test_packet_and_guard_limits_are_fixed_before_any_send(tmp_path):
    data = packet()
    smoke.check_agent_packet(data)
    guard = smoke.AgentRequestGuard(Decimal(2), Decimal(8))
    guard.begin_case(data["cases"][0])
    guard.stage = "planning_1"
    for _ in range(smoke.AGENT_MAX_PER_CASE):
        asyncio.run(guard.before_send(planning_request()))
    with pytest.raises(smoke.SmokeStopped, match="allowance"):
        asyncio.run(guard.before_send(planning_request()))
    assert guard.case_counts["AG-01"] == smoke.AGENT_MAX_PER_CASE
    assert len(guard.attempts) == smoke.AGENT_MAX_PER_CASE


def test_batch_limit_is_twelve_across_cases():
    data = packet()
    guard = smoke.AgentRequestGuard(Decimal(2), Decimal(8))
    for case in data["cases"]:
        guard.begin_case(case)
        guard.stage = "planning_1"
        for _ in range(smoke.AGENT_MAX_PER_CASE):
            asyncio.run(guard.before_send(planning_request()))
    with pytest.raises(smoke.SmokeStopped, match="allowance"):
        asyncio.run(guard.before_send(planning_request()))
    assert len(guard.attempts) == smoke.AGENT_MAX_BATCH


def test_dynamic_request_hashes_are_recorded_and_context_source_is_guarded():
    data = packet()
    case = data["cases"][0]
    guard = smoke.AgentRequestGuard(Decimal(2), Decimal(8))
    guard.begin_case(case)
    guard.stage = "planning_1"
    asyncio.run(guard.before_send(planning_request()))
    changed = planning_request()
    changed["messages"][0]["content"] = "different legitimate tool result"
    guard.stage = "planning_2"
    asyncio.run(guard.before_send(changed))
    assert guard.attempts[0]["requestSha256"] != guard.attempts[1]["requestSha256"]

    contexts = build_evidence_contexts(smoke._agent_result(case), max_evidence=2)
    guard.validate_contexts(contexts)
    bad = contexts[0].model_copy(
        update={
            "evidence": [
                contexts[0].evidence[0].model_copy(update={"file_path": "project/other.py"})
            ]
        }
    )
    with pytest.raises(smoke.SmokeStopped, match="does not match packet"):
        guard.validate_contexts([bad])


def test_agent_rejects_same_path_snippet_and_citation_mismatch():
    data = packet()
    case = data["cases"][0]
    guard = smoke.AgentRequestGuard(Decimal(2), Decimal(8))
    guard.begin_case(case)
    contexts = build_evidence_contexts(smoke._agent_result(case), max_evidence=2)
    tampered_snippet = contexts[0].model_copy(
        update={
            "evidence": [
                contexts[0].evidence[0].model_copy(update={"snippet": "same path, changed text"})
            ]
        }
    )
    with pytest.raises(smoke.SmokeStopped, match="does not match packet"):
        guard.validate_contexts([tampered_snippet])
    mismatched_citation = contexts[0].model_copy(
        update={"evidence": [contexts[0].evidence[0].model_copy(update={"citation_id": "R1-E2"})]}
    )
    with pytest.raises(smoke.SmokeStopped, match="does not match packet"):
        guard.validate_contexts([mismatched_citation])


def test_agent_history_identity_and_content_must_match_packet():
    data = packet()
    case = data["cases"][2]
    guard = smoke.AgentRequestGuard(Decimal(2), Decimal(8))
    guard.begin_case(case)
    changed = dict(case["history"])
    changed["previousExplanation"] = "tampered history"
    with pytest.raises(smoke.SmokeStopped, match="identity/content changed"):
        guard.validate_history(changed)
    changed_identity = dict(case["history"])
    changed_identity["previousReportId"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    with pytest.raises(smoke.SmokeStopped, match="identity/content changed"):
        guard.validate_history(changed_identity)


def test_agent_missing_usage_becomes_hard_stop_and_does_not_run_next_case(monkeypatch, tmp_path):
    data = packet()
    calls = []

    def reply(request):
        calls.append(request)
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
                                                "requirement_id": data["cases"][0]["requirementId"],
                                                "query": "rollback",
                                            }
                                        ),
                                    }
                                }
                            ]
                        }
                    }
                ],
            },
        )

    provider = DeepSeekProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(reply),
    )
    monkeypatch.setattr(smoke, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(smoke, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")

    report = asyncio.run(
        smoke.execute_agent(data, tmp_path / "hard-stop.json", (Decimal(2), Decimal(8)))
    )

    assert report["status"] == "stopped"
    assert report["errorType"] == "AgentHardStop"
    assert report["externalRequests"] == 1
    assert len(report["results"]) == 1
    assert report["results"][0]["status"] == "hard_stop"
    assert report["results"][0]["humanReview"] is None
    assert "usage" in report["stopReason"].lower()
    assert len(calls) == 1


def test_workflow_uses_explicit_provider_override(monkeypatch):
    from app.agents.evidence_workflow import run_evidence_workflow

    data = packet()
    case = data["cases"][1]
    calls = []
    other_calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(answer(case, "R1-E1"), ensure_ascii=False)}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

    provider = DeepSeekProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    other = DeepSeekProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(lambda request: other_calls.append(request)),
    )
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: other)
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_max_retrieval_calls", 2)

    outcome = asyncio.run(
        run_evidence_workflow(
            smoke._agent_result(case),
            provider_override=provider,
        )
    )

    assert outcome.analysis is not None and not outcome.fallback_used
    assert len(calls) == 1
    assert other_calls == []


def test_agent_model_stop_is_not_labeled_program_skip(monkeypatch, tmp_path):
    data = packet()
    guard_holder = {}

    def handler(request):
        assert settings.ai_per_report_input_token_limit == 40_000
        body = json.loads(request.content)
        guard = guard_holder["guard"]
        case = next(row for row in data["cases"] if row["id"] == guard.case_id)
        if "tools" in body:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": ""}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 5},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(answer(case, "R1-E1"), ensure_ascii=False)}}
                ],
                "usage": {"prompt_tokens": 150, "completion_tokens": 100},
            },
        )

    provider = DeepSeekProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    original_guard = smoke.AgentRequestGuard

    def make_guard(*args, **kwargs):
        guard = original_guard(*args, **kwargs)
        guard_holder["guard"] = guard
        return guard

    monkeypatch.setattr(smoke, "AgentRequestGuard", make_guard)
    monkeypatch.setattr(smoke, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(smoke, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", 40_000)

    report = asyncio.run(
        smoke.execute_agent(data, tmp_path / "model-stop.json", (Decimal(2), Decimal(8)))
    )

    assert report["externalRequests"] == 5
    assert report["results"][0]["status"] == "model_stopped"
    assert report["results"][1]["status"] == "program_skipped_planning"
    assert report["results"][2]["status"] == "model_stopped"
    assert all(row["accepted"] for row in report["results"])
    assert settings.ai_per_report_input_token_limit == 40_000


def test_agent_full_request_cap_includes_tool_schema_before_reservation():
    data = packet()
    guard = smoke.AgentRequestGuard(Decimal(2), Decimal(8))
    guard.begin_case(data["cases"][0])
    guard.stage = "planning_1"
    request = planning_request()
    request["tools"][0]["function"]["parameters"]["description"] = "x" * smoke.AGENT_INPUT_LIMIT
    with pytest.raises(smoke.SmokeStopped, match="input contract"):
        asyncio.run(guard.before_send(request))
    assert guard.attempts == []
    assert guard.reserved == 0


def test_full_agent_chain_uses_mock_transport_and_real_workflow(monkeypatch, tmp_path):
    data = packet()
    calls = []
    guard_holder = {}

    def handler(request):
        body = json.loads(request.content)
        guard = guard_holder["guard"]
        case = next(row for row in data["cases"] if row["id"] == guard.case_id)
        calls.append((guard.case_id, guard.stage, body))
        if "tools" in body:
            if guard.case_id == "AG-01":
                return tool_response("retrieve_more_evidence", case)
            if guard.case_id == "AG-03":
                return tool_response("get_previous_report_context", case)
            raise AssertionError("AG-02 must be program-skipped before planning")
        citation = "R1-E3" if guard.case_id == "AG-01" else "R1-E1"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(answer(case, citation), ensure_ascii=False)}}
                ],
                "usage": {"prompt_tokens": 150, "completion_tokens": 100},
            },
        )

    provider = DeepSeekProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    other_calls = []
    other = DeepSeekProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(lambda request: other_calls.append(request)),
    )
    original_guard = smoke.AgentRequestGuard

    def make_guard(*args, **kwargs):
        guard = original_guard(*args, **kwargs)
        guard_holder["guard"] = guard
        return guard

    monkeypatch.setattr(smoke, "AgentRequestGuard", make_guard)
    monkeypatch.setattr(smoke, "get_ai_provider", lambda: provider)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: other)
    monkeypatch.setattr(smoke, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_max_retrieval_calls", 2)

    report = asyncio.run(
        smoke.execute_agent(data, tmp_path / "agent-report.json", (Decimal(2), Decimal(8)))
    )

    assert report["status"] == "structural_checks_complete_human_review_pending", report
    assert report["externalRequests"] == 5, report
    assert [row["id"] for row in report["results"]] == ["AG-01", "AG-02", "AG-03"]
    assert report["results"][0]["toolCalls"][0]["status"] == "completed"
    assert report["results"][0]["analysis"]["items"][0]["citation_ids"] == ["R1-E3"]
    assert report["results"][1]["toolCalls"] == []
    assert report["results"][1]["status"] == "program_skipped_planning"
    assert report["results"][2]["toolCalls"][0]["tool"] == "get_previous_report_context"
    assert "historyContext" not in report["results"][2]
    assert (
        not (tmp_path / "agent-report.json").read_text(encoding="utf-8").count("synthetic-not-real")
    )
    assert all(row["humanReview"] is None for row in report["results"])
    assert len(calls) == 5
    assert other_calls == []


def test_agent_checkpoint_failure_is_hard_stop_before_post():
    data = packet()
    guard = smoke.AgentRequestGuard(Decimal(2), Decimal(8))
    guard.begin_case(data["cases"][0])
    guard.stage = "analysis"

    def fail():
        raise RuntimeError("synthetic receipt write failure")

    guard.checkpoint = fail
    with pytest.raises(smoke.SmokeStopped, match="checkpoint"):
        asyncio.run(guard.before_send(analysis_request()))
    assert guard.stopped and guard.hard_stop_reason == "checkpoint_failed"
    assert len(guard.attempts) == 1
    with pytest.raises(smoke.SmokeStopped):
        asyncio.run(guard.before_send(analysis_request()))


def test_agent_source_mismatch_becomes_hard_stop_without_post(monkeypatch, tmp_path):
    data = packet()
    original = smoke._agent_result

    def tampered(row):
        result = original(row)
        item = result.items[0]
        bad = replace(item.evidence_list[0], snippet="same path, tampered text")
        updated = replace(item, evidence=bad, evidence_list=[bad, *item.evidence_list[1:]])
        return replace(result, items=[updated])

    calls = []
    provider = DeepSeekProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(lambda request: calls.append(request)),
    )
    monkeypatch.setattr(smoke, "_agent_result", tampered)
    monkeypatch.setattr(smoke, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(smoke, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")

    report = asyncio.run(
        smoke.execute_agent(data, tmp_path / "source-stop.json", (Decimal(2), Decimal(8)))
    )

    assert report["status"] == "stopped"
    assert report["errorType"] == "AgentHardStop"
    assert report["externalRequests"] == 0
    assert len(report["results"]) == 1
    assert report["results"][0]["status"] == "hard_stop"
    assert calls == []


def test_agent_missing_usage_stops_and_keeps_reservation():
    data = packet()
    guard = smoke.AgentRequestGuard(Decimal(2), Decimal(8))
    guard.begin_case(data["cases"][0])
    guard.stage = "analysis"
    attempt = asyncio.run(guard.before_send(analysis_request()))
    with pytest.raises(smoke.SmokeStopped):
        asyncio.run(guard.after_response(attempt, {"choices": []}, 1))
    with pytest.raises(smoke.SmokeStopped):
        asyncio.run(guard.before_send(analysis_request()))
    assert len(guard.attempts) == 1 and guard.reserved == Decimal("0.0496")


def test_agent_provider_retry_cannot_bypass_guard(monkeypatch):
    data = packet()
    guard = smoke.AgentRequestGuard(Decimal(2), Decimal(8))
    guard.begin_case(data["cases"][0])
    guard.stage = "analysis"
    calls = []

    def reply(req):
        calls.append(req)
        return httpx.Response(503, json={"usage": {"prompt_tokens": 1, "completion_tokens": 0}})

    provider = DeepSeekProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=1,
        max_attempts=3,
        transport=httpx.MockTransport(reply),
    )
    provider.durable_observer = guard
    with pytest.raises(smoke.SmokeStopped):
        asyncio.run(provider._completion(analysis_request()))
    assert len(calls) == len(guard.attempts) == 1
    with pytest.raises(smoke.SmokeStopped):
        asyncio.run(guard.before_send(analysis_request()))


def test_agent_packet_source_drift_is_rejected():
    data = packet()
    data["sourceHashes"]["backend/app/agents/evidence_workflow.py"] = "0" * 64
    with pytest.raises(smoke.SmokeStopped, match="source changed"):
        smoke.check_agent_packet(data)


def test_agent_batch_claim_is_exclusive(tmp_path):
    smoke.claim_batch(tmp_path, smoke.AGENT_BATCH_ID)
    with pytest.raises(FileExistsError):
        smoke.claim_batch(tmp_path, smoke.AGENT_BATCH_ID)


def test_offline_agent_cli_does_not_construct_provider(monkeypatch):
    monkeypatch.setattr(smoke, "get_ai_provider", lambda: pytest.fail("provider constructed"))
    monkeypatch.setattr("sys.argv", ["smoke", "--agent", "--packet", str(packet_path())])
    assert smoke.main() == 0
