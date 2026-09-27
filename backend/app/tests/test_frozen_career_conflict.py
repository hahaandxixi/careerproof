"""Replay an actually saved contradictory answer through current persisted routes."""

import copy
import json
import secrets
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx

from app.agents.provider import DeepSeekProvider
from app.tests.frozen_career_conflict import (
    FROZEN_DRAFT,
    FROZEN_PLAN,
    SOURCE_RECORD_SHA256,
)
from app.tests.test_real_matching import matching_db  # noqa: F401
from evals.verify_two_sided_api import SYNTHETIC_SECRET, run_case


async def test_saved_real_conflict_is_rejected_persisted_and_owner_scoped(
    matching_db,  # noqa: F811
    monkeypatch,
):
    app, factory = matching_db

    @asynccontextmanager
    async def isolated(record):
        yield app, factory

    monkeypatch.setattr("evals.verify_two_sided_api.isolated_api", isolated)
    requests = []

    async def handle(request):
        body = json.loads(request.content)
        assert SYNTHETIC_SECRET not in json.dumps(body)
        supplied = json.loads(body["messages"][1]["content"])
        assert "description" not in supplied  # no enterprise model generation
        jobs = supplied["jobs"]
        assert len(jobs) == 1
        requests.append(body)
        answer = copy.deepcopy(FROZEN_PLAN)
        answer["focusJobId"] = jobs[0]["jobId"]
        answer["advice"][0]["jobId"] = jobs[0]["jobId"]
        # Only synthetic identity binding changes; the historical wording and
        # citations are not rewritten to manufacture a failure.
        assert set(answer["advice"][0]["citationIds"]).issubset(
            {e["citationId"] for e in jobs[0]["evidence"]}
        )
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}],
                # Synthetic transport counters must not be described as new official usage.
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    def offline_provider():
        return DeepSeekProvider(
            api_key="synthetic-key",
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout_seconds=5,
            max_attempts=1,
            transport=httpx.MockTransport(handle),
        )

    monkeypatch.setattr("app.services.career_planning.get_ai_provider", offline_provider)

    def forbidden_enterprise_provider():
        raise AssertionError("Frozen draft replay must not generate an enterprise answer")

    monkeypatch.setattr("app.services.job_drafting.get_ai_provider", forbidden_enterprise_provider)
    record = {}
    await run_case(record, (copy.deepcopy(FROZEN_DRAFT), SOURCE_RECORD_SHA256))
    plan = record["plan"]
    assert len(requests) == 1  # no hidden retry or corrective model generation
    assert plan["aiStatus"] == "visible_code_fact_conflict"
    assert plan["aiFallbackUsed"] and plan["aiPlan"] is None
    assert plan["recommendations"] and record["planSourcesExact"]
    assert plan == record["planReloaded"]
    assert record["foreignTaskStatuses"] == [404]
    assert record["enterpriseLatestPlan"] is None
    issues = plan["aiValidationIssues"]
    assert len(issues) == 1
    assert issues[0]["rejectedClaim"] == (
        "但输入校验与错误响应、接口测试代码及运行记录在材料中尚未展示"
    )
    assert issues[0]["rejectedClaim"] in FROZEN_PLAN["comparison"]
    assert "尚未展示" in issues[0]["rejectedClaim"]
    assert issues[0]["citationIds"]
    assert set(issues[0]["citationIds"]).issubset(
        {e["citationId"] for e in plan["recommendations"][0]["evidence"]}
    )
    assert len(record["usage"]) == 1  # persisted synthetic usage, not billed usage
    assert FROZEN_PLAN["focusJobId"] == "__synthetic_job__"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://synthetic"
    ) as unrelated_student:
        registered = await unrelated_student.post(
            "/api/v1/auth/register",
            json={
                "email": uuid4().hex + "@example.com",
                "password": secrets.token_urlsafe(24),
                "displayName": "合成无关学生",
                "role": "student",
            },
        )
        assert registered.status_code == 201
        assert (
            await unrelated_student.get("/api/v1/analysis-tasks/" + plan["planId"])
        ).status_code == 404
        latest = await unrelated_student.get("/api/v1/career-plans/latest")
        assert latest.status_code == 200 and latest.json()["data"] is None
