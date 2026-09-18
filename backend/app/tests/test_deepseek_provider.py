import json

import httpx
import pytest
from pydantic import SecretStr

from app.agents.contracts import validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.provider import DeepSeekProvider, ProviderOutputTruncatedError, get_ai_provider
from app.core.config import settings
from app.tests.test_ai_evidence_workflow import evidenced_result


def provider(**overrides):
    return DeepSeekProvider(
        **{
            "api_key": "synthetic-deepseek-key",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-flash",
            "timeout_seconds": 5,
            **overrides,
        }
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com",
        "https://chat.deepseek.com",
        "https://api.deepseek.example.com",
        "https://api.deepseek.com/v1",
    ],
)
def test_only_official_deepseek_api_endpoint_is_allowed(url):
    with pytest.raises(ValueError, match="official API endpoint"):
        provider(base_url=url)


@pytest.mark.parametrize("model", ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro"])
def test_only_cost_guarded_flash_model_is_allowed(model):
    with pytest.raises(ValueError, match="cost guard"):
        provider(model=model)


async def test_deepseek_json_evidence_request_uses_non_thinking_mode():
    contexts = build_evidence_contexts(evidenced_result())

    async def handler(request):
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer synthetic-deepseek-key"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["response_format"] == {"type": "json_object"}
        assert body["max_tokens"] == settings.ai_per_report_output_token_limit
        assert "JSON" in body["messages"][0]["content"]
        citation = contexts[0].evidence[0].citation_id
        answer = {
            "summary": "材料中存在路由声明，运行结果仍需核验。",
            "items": [
                {
                    "requirement_id": contexts[0].requirement_id,
                    "explanation": "片段中存在路由声明。",
                    "citation_ids": [citation],
                    "information_gap": "运行结果和本人贡献未核验。",
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
                                "reason": "函数为空实现。",
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
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": json.dumps(answer)}}],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 40,
                    "prompt_tokens_details": {"cached_tokens": 8},
                },
            },
        )

    result = await provider(transport=httpx.MockTransport(handler)).analyze_evidence(
        contexts=contexts
    )
    validate_grounded_analysis(contexts, result)
    assert result.model == "deepseek-flash"
    assert result.usage.input_tokens == 80
    assert result.usage.output_tokens == 40
    assert result.usage.cache_hit_tokens == 8


async def test_input_budget_blocks_request_before_network(monkeypatch):
    contexts = build_evidence_contexts(evidenced_result())

    async def forbidden_request(request):
        pytest.fail(f"Request must be blocked before network: {request.url}")

    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", 1000)
    with pytest.raises(ValueError, match="AI_PER_REPORT_INPUT_TOKEN_LIMIT"):
        await provider(
            transport=httpx.MockTransport(forbidden_request), max_attempts=1
        ).analyze_evidence(contexts=contexts)


async def test_single_missing_item_brace_is_repaired_and_recorded():
    contexts = build_evidence_contexts(evidenced_result())
    requirement_id = contexts[0].requirement_id
    citation = contexts[0].evidence[0].citation_id
    valid_content = json.dumps(
        {
            "summary": "材料中存在路由声明，运行结果待核验。",
            "items": [
                {
                    "requirement_id": requirement_id,
                    "explanation": "片段中存在路由声明。",
                    "citation_ids": [citation],
                    "information_gap": "运行结果和本人贡献待核验。",
                    "suggestion": "补充运行记录并说明本人贡献。",
                    "confidence": 0.5,
                    "rating": None,
                }
            ],
        },
        ensure_ascii=False,
    )
    content = valid_content[:-3] + valid_content[-2:]

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    result = await instance.analyze_evidence(contexts=contexts)

    assert result.summary.startswith("材料中存在")
    assert instance.json_repair_count == 1


async def test_truncated_json_keeps_usage_and_reports_token_limit():
    contexts = build_evidence_contexts(evidenced_result())

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [
                    {
                        "message": {"content": '{"summary":"未完成","items":['},
                        "finish_reason": "length",
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 3999},
            },
        )

    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    with pytest.raises(ProviderOutputTruncatedError, match="token limit"):
        await instance.analyze_evidence(contexts=contexts)

    assert instance.last_finish_reason == "length"
    assert instance.combined_usage().input_tokens == 120
    assert instance.combined_usage().output_tokens == 3999


async def test_deepseek_summary_exposes_sanitized_usage():
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": '{"summary":"合成摘要"}'}}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "prompt_tokens_details": {"cached_tokens": 3},
                },
            },
        )

    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    result = await instance.summarize_match(
        deterministic_summary="合成规则结果", job_title="合成岗位", candidate_name="不外发"
    )
    assert result.summary == "合成摘要"
    assert instance.last_usage.input_tokens == 12
    assert instance.last_usage.output_tokens == 4
    assert instance.last_usage.cache_hit_tokens == 3


async def test_deepseek_retrieval_planner_uses_official_tool_protocol():
    contexts = build_evidence_contexts(evidenced_result(), max_evidence=2)

    async def handler(request):
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        assert body["tool_choice"] == "auto"
        assert body["tools"][0]["function"]["name"] == "retrieve_more_evidence"
        assert "当前上传索引仍有未展示候选" in body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": "无需补检索", "tool_calls": []}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 3},
            },
        )

    instance = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    assert await instance.plan_evidence_retrieval(contexts=contexts) is None
    assert instance.planning_usage.input_tokens == 20


def test_deepseek_provider_selection_and_disabled_mode(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", SecretStr("synthetic-deepseek-key"))
    assert get_ai_provider().name == "mock"
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    selected = get_ai_provider()
    assert selected.name == "deepseek" and selected.model == "deepseek-flash"


def test_deepseek_key_is_required_only_when_external_calls_are_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        get_ai_provider()
