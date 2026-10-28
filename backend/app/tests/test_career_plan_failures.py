"""Career-only failure categories; real provider parsing over offline MockTransport."""

import json
import logging
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.agents.provider import DeepSeekProvider
from app.core.config import settings
from app.models.analysis import AnalysisTask
from app.schemas.analysis import CareerPlanRequest
from app.services import career_planning
from app.tests.test_career_change_attribution import JOB, OLD_VERSION, result


class RecordingSession:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    async def flush(self):
        for row in self.rows:
            if isinstance(row, AnalysisTask) and row.id is None:
                row.id = uuid4()

    async def commit(self):
        pass


@pytest.fixture
def planning(monkeypatch):
    async def recommend(*_):
        return result()

    async def latest(*_):
        return None

    async def budget(*_):
        return True, None, {}

    monkeypatch.setattr(career_planning, "recommend_jobs", recommend)
    monkeypatch.setattr(career_planning, "latest_plan", latest)
    monkeypatch.setattr(career_planning, "_daily_ai_budget", budget)
    return RecordingSession(), CareerPlanRequest(
        resumeVersionId=OLD_VERSION, externalAiConsent=True,
    ), SimpleNamespace(id=uuid4())


@pytest.mark.parametrize("enabled,provider_name,expected", [
    (False, "deepseek", "external_ai_disabled"),
    (True, "mock", "mock_provider"),
    (True, "deepseek", "model_configuration_error"),
])
async def test_unavailable_configuration_never_sends_or_saves_a_plan(
    planning, monkeypatch, enabled, provider_name, expected,
):
    monkeypatch.setattr(settings, "ai_external_enabled", enabled)
    monkeypatch.setattr(settings, "ai_provider", provider_name)
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    # The actual factory must handle disabled/mock/missing-key settings, not a fake provider.
    from app.agents.provider import get_ai_provider
    monkeypatch.setattr(career_planning, "get_ai_provider", get_ai_provider)

    def no_network(*_, **__):
        raise AssertionError("Configuration failure must never construct an HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", no_network)
    session, request, user = planning
    for _ in range(2):
        response = await career_planning.create_career_plan(session, request, user)
        assert response.ai_status == expected
        assert response.ai_plan is None and response.ai_fallback_used
        assert response.plan_id is None and response.recommendations
    assert session.rows == []


def answer():
    return {"comparison": "当前引用不足，请补充可核对的实现材料。", "focusJobId": str(JOB),
            "advice": [{"jobId": str(JOB), "reason": "当前没有可定位的SQL实现。",
                        "keyGap": "SQL实现材料待补充。", "nextTask": "提交SQL查询源码。",
                        "taskPlan": {"deliverable": "SQL查询源码", "steps": ["编写SQL查询"],
                                     "acceptanceChecks": ["提供可定位的源码片段"]},
                        "citationIds": []}]}


@pytest.mark.parametrize("fault,expected,stage", [
    ("timeout", "model_timeout", "model_request"),
    ("network", "model_network_error", "model_request"),
    ("protocol", "model_network_error", "model_request"),
    (400, "model_request_rejected", "model_request"),
    (401, "model_auth_error", "model_request"),
    (402, "model_quota_exceeded", "model_request"),
    (403, "model_auth_error", "model_request"),
    (429, "model_rate_limited", "model_request"),
    (503, "model_http_error", "model_request"),
    ("json", "model_json_invalid", "model_request"),
    ("truncated", "model_output_truncated", "model_request"),
    ("truncated-schema", "model_output_truncated", "output_schema"),
    ("schema", "model_output_schema_invalid", "output_schema"),
    ("array", "model_output_schema_invalid", "model_request"),
    ("internal", "model_internal_error", "model_request"),
    ("citation", "model_business_validation_failed", "business_validation"),
    ("valid", "validated", None),
])
async def test_real_provider_failure_stage_is_safe_and_specific(
    planning, monkeypatch, caplog, fault, expected, stage,
):
    requests = []

    async def handler(request):
        requests.append(request)
        assert json.loads(request.content)["max_tokens"] == 1500, "no speculative budget increase"
        if fault == "timeout":
            raise httpx.ReadTimeout("synthetic-private-material", request=request)
        if fault == "network":
            raise httpx.ConnectError("synthetic-private-material", request=request)
        if fault == "protocol":
            raise httpx.RemoteProtocolError("synthetic-private-material", request=request)
        if fault == "internal":
            raise RuntimeError("synthetic-private-material")
        if isinstance(fault, int):
            return httpx.Response(fault, json={"error": "synthetic-private-material"})
        body = answer()
        if fault == "citation":
            body["advice"][0]["citationIds"] = ["cross-job-secret-citation"]
        content = '{"comparison":"' if fault in {"json", "truncated"} else json.dumps(
            [] if fault == "array" else
            {} if fault in {"schema", "truncated-schema"} else body, ensure_ascii=False,
        )
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "length" if fault in {"truncated", "truncated-schema"} else "stop",
            "message": {"content": content},
        }], "usage": {"prompt_tokens": 20, "completion_tokens": 10}})

    provider = DeepSeekProvider(
        api_key="synthetic-key", base_url="https://api.deepseek.com", model="deepseek-flash",
        timeout_seconds=1, max_attempts=1, transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(career_planning, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    session, request, user = planning
    with caplog.at_level(logging.WARNING, logger=career_planning.__name__):
        response = await career_planning.create_career_plan(session, request, user)
    assert len(requests) == 1
    assert response.ai_status == expected
    assert response.plan_id and response.recommendations
    assert bool(response.ai_plan) == (fault == "valid")
    records = [r for r in caplog.records if r.name == career_planning.__name__]
    if stage:
        assert len(records) == 1 and records[0].stage == stage
        assert records[0].reason == expected
        safe = str(vars(records[0]))
        assert "synthetic-key" not in safe and "synthetic-private-material" not in safe
        assert "cross-job-secret-citation" not in safe
    else:
        assert not records


async def test_daily_limit_keeps_candidates_without_request_or_new_history(planning, monkeypatch):
    async def denied(*_):
        return False, "daily_report_limit", {}

    async def forbidden(_):
        raise AssertionError("No HTTP request is allowed after a denied budget")

    monkeypatch.setattr(career_planning, "_daily_ai_budget", denied)
    monkeypatch.setattr(career_planning, "get_ai_provider", lambda: DeepSeekProvider(
        api_key="synthetic-key", base_url="https://api.deepseek.com", model="deepseek-flash",
        timeout_seconds=1, max_attempts=1, transport=httpx.MockTransport(forbidden),
    ))
    session, request, user = planning
    response = await career_planning.create_career_plan(session, request, user)
    assert response.ai_status == "daily_report_limit" and response.recommendations
    assert response.plan_id is None and session.rows == []


async def test_local_input_budget_does_not_send_or_save(planning, monkeypatch):
    async def forbidden(_):
        raise AssertionError("No HTTP request is allowed past the input budget")

    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", 1)
    monkeypatch.setattr(career_planning, "get_ai_provider", lambda: DeepSeekProvider(
        api_key="synthetic-key", base_url="https://api.deepseek.com", model="deepseek-flash",
        timeout_seconds=1, max_attempts=1, transport=httpx.MockTransport(forbidden),
    ))
    session, request, user = planning
    response = await career_planning.create_career_plan(session, request, user)
    assert response.ai_status == "model_request_budget" and response.recommendations
    assert response.plan_id is None and session.rows == []
