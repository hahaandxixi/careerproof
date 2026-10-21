from zipfile import ZipFile

from evals.verify_agent_run import verify


def fixture(tmp_path):
    archive = tmp_path / "material.zip"
    with ZipFile(archive, "w") as handle:
        handle.writestr("app.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    report = {
        "items": [{
            "skill": "FastAPI",
            "requirementTitle": "FastAPI",
            "verdict": "supported",
            "evidenceLevel": 1,
            "ratingCriteria": [{"criterion": "relevance", "supported": True}],
            "evidenceList": [{
                "citationId": "R1-E1", "filePath": "version/app.py",
                "lineStart": 1, "lineEnd": 1, "snippet": "from fastapi import FastAPI",
            }],
            "aiCitationIds": ["R1-E1"],
        }],
        "aiToolCalls": [{"tool": "retrieve_more_evidence", "status": "not_requested"}],
        "aiUsage": {"input_tokens": 10, "output_tokens": 2},
    }
    attempts = [{"step": "analysis"}]
    usage = [{"input_tokens": 10, "output_tokens": 2}]
    return archive, report, attempts, usage


def test_valid_fixture_passes_but_tool_is_unverified(tmp_path):
    archive, report, attempts, usage = fixture(tmp_path)
    result = verify(report, archive, attempts, usage, min_items=1)
    assert result["status"] == "pass"
    assert any("tool execution" in row for row in result["unverified"])


def test_wrong_line_and_path_fail(tmp_path):
    archive, report, attempts, usage = fixture(tmp_path)
    report["items"][0]["evidenceList"][0]["lineEnd"] = 99
    assert verify(report, archive, attempts, usage, min_items=1)["status"] == "fail"

    archive, report, attempts, usage = fixture(tmp_path)
    report["items"][0]["evidenceList"][0]["filePath"] = "version/not-there.py"
    assert verify(report, archive, attempts, usage, min_items=1)["status"] == "fail"


def test_level_above_locally_supported_criteria_fails(tmp_path):
    archive, report, attempts, usage = fixture(tmp_path)
    report["items"][0]["evidenceLevel"] = 2
    result = verify(report, archive, attempts, usage, min_items=1)
    assert result["status"] == "fail"
    assert any("exceeds locally supported" in row for row in result["failures"])


def test_completed_tool_without_citation_fails(tmp_path):
    archive, report, attempts, usage = fixture(tmp_path)
    report["aiToolCalls"] = [{"tool": "retrieve_more_evidence", "status": "completed"}]
    result = verify(report, archive, attempts, usage, min_items=1)
    assert result["status"] == "fail"
    assert any("completed tool call" in row for row in result["failures"])


def test_missing_usage_fails(tmp_path):
    archive, report, attempts, _usage = fixture(tmp_path)
    result = verify(report, archive, attempts, [], min_items=1)
    assert result["status"] == "fail"
    assert any("trusted usage" in row for row in result["failures"])
