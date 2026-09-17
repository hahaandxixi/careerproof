import json

import httpx
import pytest
from pydantic import SecretStr

from app.agents.contracts import validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts, run_evidence_workflow
from app.agents.provider import ZhipuProvider, get_ai_provider
from app.core.config import settings
from app.tests.test_ai_evidence_workflow import evidenced_result


def provider(**overrides):
    return ZhipuProvider(
        **{
            "api_key": "synthetic-zhipu-key",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4.7-flash",
            "timeout_seconds": 5,
            **overrides,
        }
    )


@pytest.mark.parametrize("model", ["glm-4.7-flashx", "glm-4.7", "glm-5"])
def test_paid_model_is_rejected_before_request(model):
    with pytest.raises(ValueError, match="paid models are blocked"):
        provider(model=model)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/api/paas/v4",
        "https://open.bigmodel.cn/api/coding/paas/v4",
        "http://open.bigmodel.cn/api/paas/v4",
    ],
)
def test_only_standard_official_endpoint_is_allowed(url):
    with pytest.raises(ValueError, match="official standard"):
        provider(base_url=url)


async def test_zhipu_json_evidence_protocol_and_usage():
    contexts = build_evidence_contexts(evidenced_result())

    async def handler(request):
        assert str(request.url) == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        assert request.headers["Authorization"] == "Bearer synthetic-zhipu-key"
        body = json.loads(request.content)
        assert body["model"] == "glm-4.7-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["response_format"] == {"type": "json_object"}
        system = body["messages"][0]
        assert system["role"] == "system"
        assert "evidence-trust-v6-consistency" in system["content"]
        assert "connection: psycopg.Connection" in system["content"]
        assert "不能执行" in system["content"]
        answer = {
            "summary": "材料中有函数文本，运行情况待核验。",
            "items": [
                {
                    "requirement_id": contexts[0].requirement_id,
                    "explanation": "片段展示函数定义，具体行为需结合原文核验。",
                    "citation_ids": [contexts[0].evidence[0].citation_id],
                    "information_gap": "运行结果及本人贡献尚未核验。",
                    "suggestion": "补充运行记录并说明本人贡献。",
                    "confidence": 0.5,
                    "rating": {
                        "level": 1,
                        "reason": "只有相关声明，函数体为空。",
                        "criteria": [
                            {
                                "criterion": key,
                                "supported": key == "relevance",
                                "citation_ids": [contexts[0].evidence[0].citation_id]
                                if key == "relevance"
                                else [],
                                "reason": "有相关文本，但未展示实质操作。",
                            }
                            for key in ("relevance", "operation", "task")
                        ],
                    },
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "model": "glm-4.7-flash",
                "choices": [{"message": {"content": json.dumps(answer)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

    result = await provider(transport=httpx.MockTransport(handler)).analyze_evidence(
        contexts=contexts
    )
    validate_grounded_analysis(contexts, result)
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 50


@pytest.mark.parametrize("code,reason", [("1302", "rate_limit"), ("1305", "provider_busy")])
async def test_zhipu_rate_limit_uses_rule_fallback_without_retry(monkeypatch, code, reason):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": {"code": code}})

    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "zhipu")
    monkeypatch.setattr(settings, "zhipu_api_key", SecretStr("synthetic-zhipu-key"))
    monkeypatch.setattr(
        "app.agents.evidence_workflow.get_ai_provider",
        lambda: provider(
            transport=httpx.MockTransport(handler),
            max_attempts=1,
        ),
    )
    outcome = await run_evidence_workflow(evidenced_result())
    assert calls == 1
    assert outcome.analysis is None
    assert outcome.fallback_used and outcome.fallback_reason == reason
    assert outcome.provider == "zhipu" and outcome.model == "glm-4.7-flash"


async def test_provider_honors_retry_after_and_emits_progress(monkeypatch):
    calls = 0
    waits = []
    progress = []

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summary":"ok"}'}}]},
        )

    async def fake_sleep(seconds):
        waits.append(seconds)

    async def record(message):
        progress.append(message)

    instance = provider(transport=httpx.MockTransport(handler), max_attempts=2)
    instance.progress_callback = record
    monkeypatch.setattr("app.agents.provider.asyncio.sleep", fake_sleep)
    result = await instance.summarize_match(
        deterministic_summary="规则结果", job_title="测试岗位", candidate_name="不会外发"
    )
    assert result.summary == "ok"
    assert calls == 2 and waits == [3]
    assert progress == ["模型暂时不可用，3秒后进行第2次有限重试"]


async def test_invalid_output_is_repaired_once(monkeypatch):
    contexts = build_evidence_contexts(evidenced_result())
    calls = 0
    progress = []

    async def record(message):
        progress.append(message)

    def answer(level, requirement_id):
        citation = contexts[0].evidence[0].citation_id
        supported = level >= 1
        return {
            "summary": "材料中存在路由声明，运行情况待核验。",
            "items": [
                {
                    "requirement_id": requirement_id,
                    "explanation": "片段显示路由装饰器。",
                    "citation_ids": [citation],
                    "information_gap": "函数行为、运行结果和本人贡献待核验。",
                    "suggestion": "补充完整实现和运行记录。",
                    "confidence": 0.5,
                    "rating": {
                        "level": level,
                        "reason": "按引用片段进行初评。",
                        "criteria": [
                            {
                                "criterion": key,
                                "supported": supported if key == "relevance" else level >= index,
                                "citation_ids": [citation]
                                if (supported if key == "relevance" else level >= index)
                                else [],
                                "reason": "仅依据可见片段。",
                            }
                            for index, key in enumerate(("relevance", "operation", "task"), 1)
                        ],
                    },
                }
            ],
        }

    async def handler(request):
        nonlocal calls
        body = json.loads(request.content)
        if "tools" in body:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "无需补检索"}}]},
            )
        calls += 1
        source = json.loads(body["messages"][1]["content"])
        if calls == 2:
            assert "validationFeedback" in source and "rejectedOutput" in source
        payload = answer(3 if calls == 1 else 1, source["requirements"][0]["requirement_id"])
        return httpx.Response(
            200,
            json={
                "model": "glm-4.7-flash",
                "choices": [{"message": {"content": json.dumps(payload)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "zhipu")
    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: instance)
    outcome = await run_evidence_workflow(evidenced_result(), progress=record)
    assert calls == 2 and outcome.repaired is True
    assert outcome.analysis.items[0].rating.level == 1
    assert outcome.analysis.usage.input_tokens == 20
    assert any("定向修正" in message for message in progress)


async def test_retrieval_planner_emits_one_validated_function_call():
    contexts = build_evidence_contexts(evidenced_result(), max_evidence=2)

    async def handler(request):
        body = json.loads(request.content)
        assert body["tool_choice"] == "auto"
        tool = body["tools"][0]["function"]
        assert tool["name"] == "retrieve_more_evidence"
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
                                                "requirement_id": contexts[0].requirement_id,
                                                "query": "FastAPI 路由函数中的实际返回行为",
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

    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    call = await instance.plan_evidence_retrieval(contexts=contexts)
    assert call is not None
    assert call.requirement_id == contexts[0].requirement_id
    assert instance.planning_usage.input_tokens == 30


async def test_invalid_retrieval_tool_call_is_rejected_without_losing_analysis(monkeypatch):
    progress = []

    async def record(message):
        progress.append(message)

    async def handler(request):
        body = json.loads(request.content)
        if "tools" in body:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "read_arbitrary_file",
                                            "arguments": '{}',
                                        }
                                    }
                                ]
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
        source = json.loads(body["messages"][1]["content"])
        requirement = source["requirements"][0]
        citation = requirement["evidence"][0]["citation_id"]
        answer = {
            "summary": "材料中存在路由声明，运行情况待核验。",
            "items": [
                {
                    "requirement_id": requirement["requirement_id"],
                    "explanation": "片段中存在路由声明。",
                    "citation_ids": [citation],
                    "information_gap": "运行结果及本人贡献尚未核验。",
                    "suggestion": "补充运行记录并说明本人贡献。",
                    "confidence": 0.5,
                    "rating": {
                        "level": 1,
                        "reason": "只确认相关线索。",
                        "criteria": [
                            {
                                "criterion": "relevance",
                                "supported": True,
                                "citation_ids": [citation],
                                "reason": "存在路由声明。",
                            },
                            {
                                "criterion": "operation",
                                "supported": False,
                                "citation_ids": [],
                                "reason": "未显示实质操作。",
                            },
                            {
                                "criterion": "task",
                                "supported": False,
                                "citation_ids": [],
                                "reason": "未显示完整任务。",
                            },
                        ],
                    },
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "model": "glm-4.7-flash",
                "choices": [{"message": {"content": json.dumps(answer)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "zhipu")
    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: instance)
    outcome = await run_evidence_workflow(evidenced_result(), progress=record)

    assert outcome.analysis is not None and not outcome.fallback_used
    assert outcome.tool_calls == (
        {
            "tool": "retrieve_more_evidence",
            "status": "rejected",
            "reason": "invalid_tool_call",
            "scope": "current-upload-index",
        },
    )
    assert outcome.analysis.usage.input_tokens == 14
    assert any("未通过边界校验" in message for message in progress)


def test_provider_selection_and_disabled_mode(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "zhipu")
    monkeypatch.setattr(settings, "zhipu_api_key", SecretStr("synthetic-zhipu-key"))
    assert get_ai_provider().name == "mock"
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    assert get_ai_provider().name == "zhipu"


async def test_missing_policy_falls_back_before_network(monkeypatch):
    def missing_policy():
        raise FileNotFoundError("synthetic missing policy")

    async def forbidden_request(request):
        pytest.fail("No request should be sent without the policy")

    monkeypatch.setattr("app.agents.provider.evidence_policy", missing_policy)
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "zhipu")
    monkeypatch.setattr(
        "app.agents.evidence_workflow.get_ai_provider",
        lambda: provider(
            transport=httpx.MockTransport(forbidden_request),
        ),
    )
    result = evidenced_result()
    score = result.overall_score
    outcome = await run_evidence_workflow(result)
    assert outcome.fallback_used and outcome.analysis is None
    assert result.overall_score == score
