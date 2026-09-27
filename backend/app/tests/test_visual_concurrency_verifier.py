"""Offline acceptance guards: do not call the model or production database."""

import copy
import json

import pytest

from app.agents.vision_provider import VISION_PROMPT_VERSION
from evals.verify_visual_concurrency import evaluate_checks, main


def valid_record():
    usage = {"input_tokens": 100, "output_tokens": 50, "cache_hit_tokens": 0, "latency_ms": 20}
    result = {
        "id": "observation",
        "status": "completed",
        "sourceHash": "hash",
        "projectVersionId": "image",
        "promptVersion": VISION_PROMPT_VERSION,
        "model": "deepseek-flash",
        "usage": usage,
    }
    return {
        "fixtureHash": "hash",
        "projectVersionId": "image",
        "cacheBefore": None,
        "responses": [
            {"httpStatus": 200, "started": 1, "finished": 3, "result": copy.deepcopy(result)},
            {"httpStatus": 200, "started": 2, "finished": 4, "result": copy.deepcopy(result)},
        ],
        "reloaded": result,
        "before": {"sourceHash": "hash", "tasks": [], "usage": []},
        "after": {
            "sourceHash": "hash",
            "tasks": [
                {
                    "id": "observation",
                    "status": "completed",
                    "sourceHash": "hash",
                    "promptVersion": VISION_PROMPT_VERSION,
                }
            ],
            "usage": [
                {
                    "taskId": "observation",
                    "model": "deepseek-flash",
                    "provider": "deepseek",
                    **usage,
                }
            ],
        },
        "enterpriseStatuses": [404, 404, 404],
    }


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "duplicate_tasks",
        "duplicate_usage",
        "prior_cache",
        "source_change",
        "not_overlapping",
        "unauthorized_read",
        "other_model",
        "usage_mismatch",
        "different_result",
        "failed_response",
        "wrong_task_source",
    ],
)
def test_verifier_rejects_false_concurrency_success(fault):
    record = valid_record()
    if fault == "duplicate_tasks":
        record["after"]["tasks"].append(copy.deepcopy(record["after"]["tasks"][0]))
    elif fault == "duplicate_usage":
        record["after"]["usage"].append(copy.deepcopy(record["after"]["usage"][0]))
    elif fault == "prior_cache":
        record["cacheBefore"] = copy.deepcopy(record["reloaded"])
    elif fault == "source_change":
        record["after"]["sourceHash"] = "other"
    elif fault == "not_overlapping":
        record["responses"][1]["started"] = 3
    elif fault == "unauthorized_read":
        record["enterpriseStatuses"][1] = 200
    elif fault == "other_model":
        record["after"]["usage"][0]["provider"] = "synthetic"
    elif fault == "usage_mismatch":
        record["after"]["usage"][0]["input_tokens"] = 101
    elif fault == "different_result":
        record["responses"][1]["result"]["id"] = "second"
    elif fault == "failed_response":
        record["responses"][1]["httpStatus"] = 429
        record["responses"][1]["result"] = None
    elif fault == "wrong_task_source":
        record["after"]["tasks"][0]["sourceHash"] = "other"
    assert all(evaluate_checks(record).values()) == (fault == "none")


@pytest.mark.parametrize("mode", ["plan", "missing_paid", "existing_output"])
def test_side_effect_gates(monkeypatch, tmp_path, mode):
    output = tmp_path / "new.json"

    def forbidden(_record):
        pytest.fail("Side effects must not start")

    monkeypatch.setattr("evals.verify_visual_concurrency.run_case", forbidden)
    flags = []
    if mode == "missing_paid":
        flags = ["--live"]
    elif mode == "existing_output":
        flags = ["--live", "--allow-paid"]
        output.write_text("original", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["verify", "--output", str(output), *flags])
    if mode == "plan":
        assert main() == 0 and not output.exists()
    else:
        with pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 2
        if mode == "existing_output":
            assert output.read_text(encoding="utf-8") == "original"
        else:
            assert not output.exists()


def test_partial_failure_is_archived_without_transport_secrets(monkeypatch, tmp_path):
    output = tmp_path / "failed.json"

    def fail(record):
        record.update(stage="upload", projectId="synthetic-project")
        raise RuntimeError("private synthetic transport detail")

    monkeypatch.setattr("evals.verify_visual_concurrency.run_case", fail)
    monkeypatch.setattr("sys.argv", ["verify", "--live", "--allow-paid", "--output", str(output)])
    assert main() == 1
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["stage"] == "upload" and saved["projectId"] == "synthetic-project"
    assert saved["errorType"] == "RuntimeError" and saved["passed"] is False
    assert "private synthetic transport detail" not in output.read_text(encoding="utf-8")
