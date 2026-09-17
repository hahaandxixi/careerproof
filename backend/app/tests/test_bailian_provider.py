import json

import httpx
import pytest

from app.agents.provider import BailianProvider


@pytest.mark.asyncio
async def test_bailian_provider_uses_minimal_input_and_validates_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = json.loads(request.content)
        assert body["model"] == "qwen-plus"
        assert body["response_format"] == {"type": "json_object"}
        user_payload = json.loads(body["messages"][1]["content"])
        assert user_payload == {"jobTitle": "后端工程师", "ruleSummary": "规则结论"}
        assert "测试学生" not in request.content.decode()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summary":"结构化结论"}'}}]},
        )

    provider = BailianProvider(
        api_key="test-secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.summarize_match(
        deterministic_summary="规则结论",
        job_title="后端工程师",
        candidate_name="测试学生",
    )

    assert result.summary == "结构化结论"


@pytest.mark.asyncio
async def test_bailian_provider_rejects_non_json_model_output() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "普通文本"}}]})

    provider = BailianProvider(
        api_key="test-secret",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="not valid JSON"):
        await provider.summarize_match(
            deterministic_summary="规则结论",
            job_title="后端工程师",
            candidate_name="测试学生",
        )


@pytest.mark.asyncio
async def test_bailian_provider_retries_rate_limit_once() -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"message": "limited"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summary":"重试成功"}'}}]},
        )

    provider = BailianProvider(
        api_key="test-secret",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.summarize_match(
        deterministic_summary="规则结论",
        job_title="后端工程师",
        candidate_name="测试学生",
    )

    assert calls == 2
    assert result.summary == "重试成功"


def test_bailian_provider_rejects_non_aliyun_endpoint() -> None:
    with pytest.raises(ValueError, match="HTTPS aliyuncs.com"):
        BailianProvider(
            api_key="test-secret",
            base_url="https://example.com/v1",
            model="qwen-plus",
            timeout_seconds=5,
        )
