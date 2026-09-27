"""Offline checks for the MCP model agent acceptance: no paid calls, no network."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.core.config import settings
from evals.verify_mcp_model_agent import (
    DEFAULT_TASK,
    bounded,
    deepseek_tools_from_mcp,
    failure_info,
    run_agent_loop,
    tool_result_content,
)


def mcp_tool(name, description, schema):
    return SimpleNamespace(name=name, description=description, inputSchema=schema)


def response(content=None, tool_calls=None, usage=None, finish_reason="stop"):
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5},
        "choices": [{"finish_reason": finish_reason, "message": message}],
    }


def tool_call(name, arguments, call_id="call-1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class FakeResult:
    def __init__(self, body, *, is_error=False):
        self.content = [SimpleNamespace(text=body)]
        self.structuredContent = None
        self.isError = is_error


def test_deepseek_tools_from_mcp_maps_schema_without_inventing_fields():
    tool = mcp_tool(
        "search_evidence", "Search saved evidence.", {"type": "object", "properties": {}}
    )
    definitions = deepseek_tools_from_mcp([tool])
    assert definitions == [
        {
            "type": "function",
            "function": {
                "name": "search_evidence",
                "description": "Search saved evidence.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


def test_deepseek_tools_from_mcp_defaults_schema_and_truncates_description():
    tool = mcp_tool("get_report_summary", "x" * 400, None)
    definition = deepseek_tools_from_mcp([tool])[0]["function"]
    assert definition["description"] == "x" * 300
    assert definition["parameters"] == {"type": "object", "properties": {}}


def test_tool_result_content_prefers_structured_content():
    structured = SimpleNamespace(structuredContent={"result": 1}, content=[])
    assert json.loads(tool_result_content(structured)) == {"result": 1}
    plain = FakeResult("text block")
    assert tool_result_content(plain) == "text block"


def test_bounded_marks_truncation():
    assert bounded("abc", 5) == ("abc", False)
    value, truncated = bounded("abcdef", 5)
    assert value == "abcde" and truncated


def test_agent_loop_records_model_chosen_tools_and_final_answer():
    rounds = [
        response(
            tool_calls=[tool_call("get_report_summary", {"report_id": "r-1"})],
            finish_reason="tool_calls",
        ),
        response(
            tool_calls=[
                tool_call("compare_reports", {"base_id": "r-0", "target_id": "r-1"}, "call-2")
            ],
            finish_reason="tool_calls",
        ),
        response(content="对比结论…"),
    ]
    executed = []
    events = []

    async def completion(request):
        return rounds.pop(0), 12

    async def execute(name, arguments):
        executed.append(name)
        return FakeResult(json.dumps({"tool": name}))

    final_answer = asyncio.run(
        run_agent_loop(
            completion,
            execute,
            events=events,
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            tools=[],
            max_rounds=4,
        )
    )
    assert executed == ["get_report_summary", "compare_reports"]
    assert final_answer == "对比结论…"
    decisions = [event["decision"] for event in events if "decision" in event]
    assert decisions == ["tool_calls", "tool_calls", "final_answer"]
    assert events[-1]["decision"] == "final_answer"
    assert events[1]["tool"] == "get_report_summary"
    assert events[1]["isError"] is False
    assert events[1]["result"] == json.dumps({"tool": "get_report_summary"})


def test_agent_loop_keeps_tool_errors_and_continues():
    rounds = [
        response(tool_calls=[tool_call("compare_reports", {"base_id": "x", "target_id": "y"})]),
        response(content="只能回答可用数据。"),
    ]
    events = []

    async def completion(request):
        return rounds.pop(0), 8

    async def execute(name, arguments):
        return FakeResult("Read-only request rejected (HTTP 404)", is_error=True)

    final_answer = asyncio.run(
        run_agent_loop(completion, execute, events=events, messages=[], tools=[], max_rounds=2)
    )
    assert events[1]["isError"] is True
    assert final_answer == "只能回答可用数据。"


def test_agent_loop_stops_when_last_round_ignores_missing_tools():
    async def completion(request):
        return response(tool_calls=[tool_call("search_evidence", {"q": "FastAPI"})]), 5

    async def execute(name, arguments):
        return FakeResult("[]")

    events = []
    final_answer = asyncio.run(
        run_agent_loop(completion, execute, events=events, messages=[], tools=[], max_rounds=3)
    )
    assert final_answer is None
    assert events[-1]["decision"] == "unexpected_tool_calls_without_tools"
    assert sum(event.get("tool") == "search_evidence" for event in events) == 2


def test_agent_loop_caps_tool_calls_per_round():
    calls = [
        tool_call("search_evidence", {"q": f"q{i}"}, f"call-{i}") for i in range(6)
    ]
    rounds = [response(tool_calls=calls, finish_reason="tool_calls"), response(content="结论。")]

    async def completion(request):
        return rounds.pop(0), 5

    async def execute(name, arguments):
        return FakeResult("[]")

    events = []
    messages: list[dict] = [{"role": "system", "content": "s"}]
    final_answer = asyncio.run(
        run_agent_loop(
            completion, execute, events=events, messages=messages, tools=[], max_rounds=2
        )
    )
    assert final_answer == "结论。"
    assert sum(event.get("tool") == "search_evidence" for event in events) == 4
    capped = [event for event in events if event.get("decision") == "tool_calls_capped"]
    assert len(capped) == 1 and capped[0]["cap"] == 4
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 6
    assert "已达上限" in tool_messages[-1]["content"]


def test_agent_loop_rejects_invalid_tool_arguments():
    async def completion(request):
        return response(
            tool_calls=[
                {"id": "c", "type": "function", "function": {"name": "t", "arguments": "{"}}
            ]
        ), 5

    async def execute(name, arguments):
        raise AssertionError("must not execute")

    with pytest.raises(ValueError, match="not valid JSON"):
        asyncio.run(
            run_agent_loop(completion, execute, events=[], messages=[], tools=[], max_rounds=1)
        )


def test_agent_loop_forces_no_tools_when_input_budget_exhausted(monkeypatch):
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", 500)
    seen_requests = []

    async def completion(request):
        seen_requests.append(request)
        return response(content="仅基于已有数据回答。"), 9

    events = []
    final_answer = asyncio.run(
        run_agent_loop(
            completion,
            execute=None,
            events=events,
            messages=[{"role": "system", "content": "x" * 2000}],
            tools=[{"type": "function", "function": {"name": "t"}}],
            max_rounds=2,
        )
    )
    assert final_answer == "仅基于已有数据回答。"
    assert seen_requests[0]["tools"] == []
    assert events[-1]["decision"] == "final_answer"
    assert events[-1]["forcedNoTools"] is True


def test_agent_loop_unexpected_tool_calls_without_tools_are_recorded(monkeypatch):
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", 500)

    async def completion(request):
        return response(
            tool_calls=[tool_call("search_evidence", {"q": "x"})], finish_reason="tool_calls"
        ), 5

    events = []
    final_answer = asyncio.run(
        run_agent_loop(
            completion,
            execute=None,
            events=events,
            messages=[{"role": "system", "content": "x" * 2000}],
            tools=[],
            max_rounds=1,
        )
    )
    assert final_answer is None
    assert events[-1]["decision"] == "unexpected_tool_calls_without_tools"


def test_failure_info_unwraps_exception_groups():
    group = ExceptionGroup("task group", [ValueError("model input exceeds limit")])
    info = failure_info(group)
    assert info["class"] == "ExceptionGroup"
    assert info["subExceptions"] == [
        {"class": "ValueError", "detail": "model input exceeds limit"}
    ]
    assert failure_info(httpx_timeout()).get("detail") is None


def httpx_timeout():
    from httpx import ReadTimeout

    return ReadTimeout("raw transport body must not be recorded")


async def test_missing_paid_flag_exits_before_any_run(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.argv",
        [
            "mcp-model-agent",
            "--base-id", "19148e76-c521-4cf7-88a6-6436a356ed21",
            "--target-id", "8c72d898-175b-48a3-8eb6-2938310aea28",
            "--output", str(tmp_path / "record.json"),
        ],
    )
    from evals.verify_mcp_model_agent import main

    with pytest.raises(SystemExit) as error:
        await main()
    assert error.value.code == 2 and not (tmp_path / "record.json").exists()


def test_default_task_contains_both_report_ids():
    text = DEFAULT_TASK.format(base="b-1", target="t-1")
    assert "b-1" in text and "t-1" in text
