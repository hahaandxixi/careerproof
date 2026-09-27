import pytest

from evals.check_output_drift import compare, main


def test_wording_only_change_is_not_rating_drift():
    baseline = {
        "results": [
            {"id": "synthetic", "accepted": True, "analysis": {"summary": "old", "items": []}}
        ]
    }
    current = {
        "results": [
            {"id": "synthetic", "accepted": True, "analysis": {"summary": "new", "items": []}}
        ]
    }
    diff = compare(baseline, current)[0]
    assert diff["status"] == "unchanged" and diff["wordingChanged"] is True


def test_failure_and_missing_case_are_preserved():
    baseline = {"results": [{"id": "synthetic", "accepted": True}, {"id": "not-run"}]}
    current = {"results": [{"id": "synthetic", "accepted": False, "httpStatus": 429}]}
    result = {row["id"]: row for row in compare(baseline, current)}
    assert result["synthetic"]["signalChanges"] == ["accepted", "httpStatus"]
    assert result["not-run"]["status"] == "not_run"


async def test_live_without_paid_flag_exits_before_loading_files(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.argv",
        ["drift", "--baseline", "not-read.json", "--output", str(tmp_path / "new.json"), "--live"],
    )
    with pytest.raises(SystemExit) as error:
        await main()
    assert error.value.code == 2 and not (tmp_path / "new.json").exists()


def rating_row():
    return {
        "id": "synthetic",
        "accepted": True,
        "externalAttempted": True,
        "productionOutcome": "ai_completed",
        "analysis": {
            "model": "synthetic-a",
            "summary": "summary",
            "items": [
                {
                    "requirement_id": "r1",
                    "explanation": "first",
                    "citation_ids": ["R1-E1"],
                    "rating": {
                        "level": 2,
                        "reason": "limited evidence",
                        "criteria": [
                            {
                                "criterion": "relevance",
                                "supported": True,
                                "reason": "related",
                                "citation_ids": ["R1-E1"],
                            },
                            {
                                "criterion": "operation",
                                "supported": False,
                                "reason": "no operation",
                                "citation_ids": [],
                            },
                        ],
                    },
                },
                {
                    "requirement_id": "r2",
                    "explanation": "second",
                    "citation_ids": [],
                    "rating": None,
                },
            ],
        },
    }


def test_reordering_requirements_and_criteria_does_not_create_drift():
    import copy

    old = rating_row()
    new = copy.deepcopy(old)
    new["analysis"]["items"].reverse()
    new["analysis"]["items"][1]["rating"]["criteria"].reverse()
    diff = compare({"results": [old]}, {"results": [new]})[0]
    assert diff["status"] == "unchanged" and not diff["wordingChanged"]


@pytest.mark.parametrize("field", ["rating_reason", "criterion_reason"])
def test_changed_decision_reason_is_visible_without_numeric_rating_drift(field):
    import copy

    old = rating_row()
    new = copy.deepcopy(old)
    rating = new["analysis"]["items"][0]["rating"]
    if field == "rating_reason":
        rating["reason"] = "changed semantic interpretation"
    else:
        rating["criteria"][0]["reason"] = "changed semantic interpretation"
    diff = compare({"results": [old]}, {"results": [new]})[0]
    assert diff["status"] == "unchanged" and diff["wordingChanged"]
    assert diff["humanSemanticReview"] == "pending"


@pytest.mark.parametrize("field", ["providerErrorCode", "productionOutcome", "externalAttempted"])
def test_failure_fallback_and_attempt_changes_are_visible(field):
    import copy

    old = rating_row()
    new = copy.deepcopy(old)
    new[field] = {
        "providerErrorCode": "synthetic_overload",
        "productionOutcome": "rules_only",
        "externalAttempted": False,
    }[field]
    diff = compare({"results": [old]}, {"results": [new]})[0]
    assert diff["status"] == "changed" and field in diff["signalChanges"]


def test_model_and_usage_changes_are_recorded_separately_from_human_review():
    import copy

    old = rating_row()
    old.update(usage={"prompt_tokens": 10, "completion_tokens": 5}, latencyMs=12)
    new = copy.deepcopy(old)
    new["analysis"]["model"] = "synthetic-b"
    new["usage"]["completion_tokens"] = 8
    new["latencyMs"] = 20
    diff = compare({"results": [old]}, {"results": [new]})[0]
    assert "model" in diff["signalChanges"]
    assert diff["usageBefore"] == old["usage"] and diff["usageAfter"] == new["usage"]
    assert diff["latencyBeforeMs"] == 12 and diff["latencyAfterMs"] == 20
    assert diff["modelComparison"] == "both_outputs"
    assert diff["humanSemanticReview"] == "pending"


@pytest.mark.parametrize(
    "results", [[{"id": "duplicated"}, {"id": "duplicated"}], [{"id": ""}], [{"id": 42}], [{}]]
)
def test_invalid_case_identity_is_rejected_instead_of_silently_overwritten(results):
    with pytest.raises(ValueError):
        compare({"results": results}, {"results": []})


def test_rules_only_pair_is_not_described_as_model_output_comparison():
    row = {"id": "synthetic", "accepted": None, "externalAttempted": False}
    diff = compare({"results": [row]}, {"results": [row]})[0]
    assert diff["modelComparison"] == "neither_output"
    assert diff["humanSemanticReview"] == "pending"
