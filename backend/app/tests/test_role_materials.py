"""Paired packs and repeatable imports, verified without paid AI or a live server."""

import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest

from evals.seed_role_materials import DESCRIPTION, seed

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("role_packs", ROOT / "demo/build_role_packs.py")
packs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packs)


def test_nine_packs_match_jobs_and_named_versions(tmp_path):
    cases = packs.build(tmp_path)
    for case in cases:
        resume = (tmp_path / case["resumeFilename"]).read_text("utf-8")
        steps = (tmp_path / case["scriptFilename"]).read_text("utf-8")
        assert case["caseId"] in resume and case["projectFilename"] in resume
        assert case["resumeName"] in steps and case["projectName"] in steps
        assert case["jobTitle"] in steps
        with ZipFile(tmp_path / case["projectFilename"]) as bundle:
            assert bundle.testzip() is None
            assert case["resumeFilename"] in bundle.read("案例说明.txt").decode()
            assert len(bundle.namelist()) >= 2
            if case["slug"] == "backend":
                assert {"app.py", "database.py", "test_app.py"} <= set(bundle.namelist())
            if case["slug"] == "frontend":
                assert "TaskList.tsx" in bundle.namelist()
            if case["slug"] == "qa":
                assert "test_tasks.py" in bundle.namelist()
            if case["slug"] == "data-engineering":
                assert "pipeline.py" in bundle.namelist()
            if case["slug"] in {"product", "operations"}:
                assert "作品说明.txt" in bundle.namelist()
    # Fixed archive metadata yields reproducible downloads.
    before = {
        case["projectFilename"]: (tmp_path / case["projectFilename"]).read_bytes() for case in cases
    }
    packs.build(tmp_path)
    assert all((tmp_path / name).read_bytes() == value for name, value in before.items())


def case_fixture():
    return packs.load_cases()[0][0]


def test_completed_named_pair_reused_without_upload_or_model_calls(tmp_path):
    case = case_fixture()
    calls = []

    def handler(request):
        calls.append(request.method)
        assert request.method == "GET"
        if request.url.path.endswith("/resumes"):
            payload = [
                {
                    "title": case["resumeName"],
                    "versions": [
                        {
                            "id": "resume-v1",
                            "originalFilename": case["resumeFilename"],
                            "status": "completed",
                        }
                    ],
                }
            ]
        elif request.url.path.endswith("/projects"):
            payload = [{"id": "project", "name": case["projectName"], "description": DESCRIPTION}]
        else:
            payload = [
                {
                    "id": "project-v1",
                    "originalFilename": case["projectFilename"],
                    "status": "completed",
                }
            ]
        return httpx.Response(200, json={"data": payload})

    records = []
    with httpx.Client(
        base_url="http://localhost/api/v1", transport=httpx.MockTransport(handler)
    ) as client:
        seed(client, [case], tmp_path, records)
    assert records[0]["resumeReused"] and records[0]["projectReused"]
    assert records[0]["stage"] == "completed" and calls == ["GET", "GET", "GET"]


@pytest.mark.parametrize("fault", ["duplicate", "failed", "wrong_filename"])
def test_import_refuses_ambiguous_or_broken_existing_resume_without_upload(fault, tmp_path):
    case = case_fixture()
    resume = {
        "title": case["resumeName"],
        "versions": [
            {
                "id": "v1",
                "originalFilename": case["resumeFilename"],
                "status": "completed",
            }
        ],
    }
    if fault == "failed":
        resume["versions"][0]["status"] = "failed"
    if fault == "wrong_filename":
        resume["versions"][0]["originalFilename"] = "other.txt"

    def handler(request):
        assert request.method == "GET"
        payload = (
            ([resume, resume] if fault == "duplicate" else [resume])
            if request.url.path.endswith("/resumes")
            else []
        )
        return httpx.Response(200, json={"data": payload})

    with (
        httpx.Client(
            base_url="http://localhost/api/v1", transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValueError),
    ):
        seed(client, [case], tmp_path, [])


def test_new_pair_uploads_with_named_files_to_correct_endpoints(monkeypatch, tmp_path):
    case = case_fixture()
    packs.build(tmp_path)
    requests = []

    def handler(request):
        requests.append(request)
        path = request.url.path
        if request.method == "GET":
            payload = []
        elif path.endswith("/resumes"):
            payload = {"versionId": "resume-v1", "taskId": "resume-task"}
        elif path.endswith("/projects"):
            payload = {"id": "project"}
            assert json.loads(request.content)["name"] == case["projectName"]
        else:
            payload = {"versionId": "project-v1", "taskId": "project-task"}
        return httpx.Response(200, json={"data": payload})

    completed = []
    monkeypatch.setattr(
        "evals.seed_role_materials.wait", lambda _c, task, timeout: completed.append(task)
    )
    records = []
    with httpx.Client(
        base_url="http://localhost/api/v1", transport=httpx.MockTransport(handler)
    ) as client:
        seed(client, [case], tmp_path, records)
    uploads = [
        r
        for r in requests
        if r.method == "POST" and "multipart/form-data" in r.headers.get("content-type", "")
    ]
    assert len(uploads) == 2
    assert case["resumeFilename"].encode() in uploads[0].content
    assert case["projectFilename"].encode() in uploads[1].content
    assert completed == ["resume-task", "project-task"]
    assert records[0]["resumeVersionId"] == "resume-v1"
    assert records[0]["projectVersionId"] == "project-v1"
