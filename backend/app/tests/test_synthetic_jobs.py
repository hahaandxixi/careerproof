"""Offline lifecycle checks; no real account, database or model calls."""

import copy
import json

import httpx
import pytest

from evals.synthetic_jobs import (
    DEMO_COMPANY,
    HISTORY_DESCRIPTION,
    TemporaryEvaluationJobs,
    is_evaluation_job,
)


def fixture_job(job_id="synthetic-job"):
    return {
        "id": job_id,
        "enterpriseId": "demo-org",
        "createdBy": "demo-owner",
        "title": "历史完整报告 injected-history（合成）20260927-163752-487512",
        "description": HISTORY_DESCRIPTION,
        "companyName": DEMO_COMPANY,
        "status": "published",
        "requirements": [{"id": "preserved-requirement"}],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"title": "数据库工程师 DBA（合成演示）"},
        {"description": "实际招聘岗位"},
        {"companyName": "其他企业"},
        {"title": "历史完整报告 自定义职业（合成）20260927-163752-487512"},
        {"title": "历史补证合成验收 20260926-234002 自定义"},
    ],
)
def test_cleanup_does_not_treat_arbitrary_demo_or_user_jobs_as_internal(change):
    assert not is_evaluation_job({**fixture_job(), **change})


@pytest.mark.parametrize(
    "title",
    [
        "历史完整报告 withdrawn-material（合成）20260927-153350-089678",
        "改要求新岗位（合成）20260927-153359-736499",
        "历史补证合成验收 20260926-234002",
    ],
)
def test_known_internal_names_are_recognized(title):
    assert is_evaluation_job({**fixture_job(), "title": title})


@pytest.mark.parametrize("failed_evaluation", [False, True])
def test_all_created_jobs_closed_even_when_evaluation_fails(failed_evaluation):
    jobs = {}
    patches = []

    def handler(request):
        if request.method == "POST":
            job = fixture_job(str(len(jobs)))
            jobs[job["id"]] = job
            return httpx.Response(201, json={"data": job})
        job = jobs[request.url.path.split("/")[-1]]
        if request.method == "PATCH":
            payload = json.loads(request.content)
            assert payload == {"status": "closed"}
            patches.append(job["id"])
            job.update(payload)
        return httpx.Response(200, json={"data": job})

    record = {}
    with httpx.Client(
        base_url="http://127.0.0.1:8000/api/v1", transport=httpx.MockTransport(handler)
    ) as client:

        def evaluate():
            with TemporaryEvaluationJobs(client, record) as scope:
                scope.create(fixture_job())
                scope.create(fixture_job())
                if failed_evaluation:
                    raise ValueError("evaluation failed")

        if failed_evaluation:
            with pytest.raises(ValueError, match="evaluation failed"):
                evaluate()
        else:
            evaluate()
    assert patches == ["0", "1"]
    assert record["jobCleanupPassed"]
    assert all(j["status"] == "closed" for j in jobs.values())
    assert all(j["requirements"] == [{"id": "preserved-requirement"}] for j in jobs.values())


@pytest.mark.parametrize("identity_changed", [False, True])
def test_cleanup_failure_is_visible_without_masking_primary_exception(identity_changed):
    patches = []
    job = fixture_job()

    def handler(request):
        if request.method == "PATCH":
            patches.append(request)
            return httpx.Response(403, json={"private": "never export transport body"})
        current = copy.deepcopy(job)
        if identity_changed:
            current["createdBy"] = "different-owner"
        return httpx.Response(200, json={"data": current})

    record = {"passed": True}
    with (
        httpx.Client(
            base_url="http://localhost:8000/api/v1", transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValueError, match="primary exception"),
        TemporaryEvaluationJobs(client, record) as scope,
    ):
        scope.track(job)
        raise ValueError("primary exception")
    assert not record["jobCleanupPassed"] and not record["passed"]
    assert len(patches) == (0 if identity_changed else 1)
    assert "never export transport body" not in json.dumps(record)


def test_cleanup_failure_fails_otherwise_successful_run_and_attempts_remaining_jobs():
    def handler(request):
        job_id = request.url.path.split("/")[-1]
        if request.method == "GET":
            return httpx.Response(200, json={"data": fixture_job(job_id)})
        if job_id == "first":
            return httpx.Response(500)
        return httpx.Response(200, json={"data": {**fixture_job(job_id), "status": "closed"}})

    record = {}
    with (
        httpx.Client(
            base_url="http://localhost:8000/api/v1", transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(RuntimeError, match="cleanup incomplete"),
        TemporaryEvaluationJobs(client, record) as scope,
    ):
        scope.track(fixture_job("first"))
        scope.track(fixture_job("second"))
    assert [item["status"] for item in record["jobCleanup"]] == ["failed", "closed"]


@pytest.mark.parametrize("base", ["https://remote.example/api/v1", "http://localhost/wrong"])
def test_cleanup_refuses_nonlocal_or_unrelated_api(base):
    with httpx.Client(base_url=base) as client, pytest.raises(ValueError, match="local"):
        TemporaryEvaluationJobs(client, {})
