"""Offline guards for real full-report history acceptance; no model or database calls."""

import copy
import hashlib

import pytest

from evals.verify_persisted_history_case import CURRENT_CODE, current_sources_exact, main


def saved_current_report():
    return {
        "items": [
            {
                "aiCitationIds": ["R1-E1"],
                "ratingCriteria": [{"citation_ids": ["R1-E1"]}],
                "evidenceList": [
                    {
                        "citationId": "R1-E1",
                        "filePath": "synthetic-version/app.py",
                        "contentHash": hashlib.sha256(CURRENT_CODE.encode()).hexdigest(),
                        "lineStart": 1,
                        "lineEnd": len(CURRENT_CODE.splitlines()),
                        "snippet": CURRENT_CODE.rstrip("\n"),
                    }
                ],
            }
        ]
    }


@pytest.mark.parametrize(
    "fault",
    [
        "old_version",
        "wrong_hash",
        "old_citation",
        "criterion_citation",
        "negative_lines",
        "duplicate_citation",
        "no_evidence",
    ],
)
def test_source_verifier_rejects_old_or_forged_current_references(fault):
    report = saved_current_report()
    evidence = report["items"][0]["evidenceList"][0]
    assert current_sources_exact(report, "synthetic-version", CURRENT_CODE)
    if fault == "old_version":
        evidence["filePath"] = "previous-version/app.py"
    elif fault == "wrong_hash":
        evidence["contentHash"] = "a" * 64
    elif fault == "old_citation":
        report["items"][0]["aiCitationIds"] = ["history-1"]
    elif fault == "criterion_citation":
        report["items"][0]["ratingCriteria"][0]["citation_ids"] = ["history-1"]
    elif fault == "negative_lines":
        evidence["lineStart"] = 0
    elif fault == "duplicate_citation":
        report["items"][0]["evidenceList"].append(copy.deepcopy(evidence))
    else:
        report["items"][0]["evidenceList"] = []
        report["items"][0]["aiCitationIds"] = []
        report["items"][0]["ratingCriteria"] = []
    assert not current_sources_exact(report, "synthetic-version", CURRENT_CODE)


def test_paid_flag_missing_exits_before_any_side_effect(monkeypatch, tmp_path):
    output = tmp_path / "new.json"
    monkeypatch.setattr("sys.argv", ["verify", "--live", "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and not output.exists()


def test_failed_live_case_preserves_partial_ids_not_raw_transport_error(monkeypatch, tmp_path):
    import json

    def failure(_scenario, record):
        record.update(stage="current_report", taskId="synthetic-task")
        raise RuntimeError("synthetic transport private text")

    monkeypatch.setattr("evals.verify_persisted_history_case.run_case", failure)
    output = tmp_path / "partial.json"
    monkeypatch.setattr("sys.argv", ["verify", "--live", "--allow-paid", "--output", str(output)])
    assert main() == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["taskId"] == "synthetic-task" and result["stage"] == "current_report"
    assert result["errorType"] == "RuntimeError" and not result["passed"]
    assert "synthetic transport private text" not in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("fault", ["baseline_fallback", "no_decrease", "history_not_read"])
def test_full_report_checks_reject_missing_baseline_or_history_evidence(fault):
    from evals.verify_persisted_history_case import evaluate_checks

    report = saved_current_report()
    report.update(
        aiFallbackUsed=False,
        aiToolCalls=[
            {
                "tool": "get_previous_report_context",
                "status": "completed",
                "previousReportId": "old",
            }
        ],
    )
    report["items"][0].update(
        aiStatus="validated", evidenceLevelSource="ai_preliminary", evidenceLevel=1
    )
    previous = copy.deepcopy(report)
    previous["items"][0]["evidenceLevel"] = 3
    record = {
        "report": report,
        "previousReport": previous,
        "previousReportId": "old",
        "baselineExternalConsent": True,
        "frozenHistory": {"previousReportId": "old"},
        "currentSourcesExact": True,
        "reloadStable": True,
        "previousReportUnchanged": True,
        "enterpriseReadStatus": 404,
    }
    assert all(evaluate_checks(record, "withdrawn-material", 1).values())
    if fault == "baseline_fallback":
        previous["aiFallbackUsed"] = True
    elif fault == "no_decrease":
        previous["items"][0]["evidenceLevel"] = 1
    else:
        report["aiToolCalls"] = []
    assert not all(evaluate_checks(record, "withdrawn-material", 1).values())
