import pytest

from app.tools.evidence_levels import classify_evidence


def test_empty_and_unsupported_are_not_level_one():
    assert classify_evidence({}, "gap")["evidence_level"] is None
    assert classify_evidence({"claimed": True}, "unsupported")["evidence_level"] is None
    assert classify_evidence({"claimed": True}, "claimed_only")["evidence_level"] is None


def test_complete_implementation_is_not_based_on_score():
    snapshot = {
        "evidenceList": [{"evidenceType": "python_code", "contextComplete": True}],
        "ruleBaseScore": 0,
    }
    assert classify_evidence(snapshot, "supported")["evidence_level"] == 3
    snapshot["evidenceList"][0]["contextComplete"] = False
    snapshot["ruleBaseScore"] = 1
    assert classify_evidence(snapshot, "supported")["evidence_level"] == 2


@pytest.mark.parametrize("skill", ["备份恢复", "索引优化"])
def test_special_requirements_cannot_be_upgraded_by_context_or_review(skill):
    snapshot = {
        "skill": skill,
        "evidenceList": [{"evidenceType": "sql_schema", "contextComplete": True}],
    }
    assert classify_evidence(snapshot, "supported", "accepted")["evidence_level"] == 2


@pytest.mark.parametrize("status", ["rejected", "corrected"])
def test_disputed_evidence_suspends_automatic_level(status):
    snapshot = {"evidenceList": [{"evidenceType": "python_code", "contextComplete": True}]}
    assert classify_evidence(snapshot, "supported", status)["evidence_level"] is None


def test_dependency_and_historical_context_are_not_full_implementation():
    assert (
        classify_evidence(
            {"evidenceList": [{"evidenceType": "dependency", "contextComplete": True}]}, "partial"
        )["evidence_level"]
        == 1
    )
    assert (
        classify_evidence({"evidence": {"evidenceType": "python_code"}}, "supported")[
            "evidence_level"
        ]
        == 2
    )


@pytest.mark.parametrize(
    "snippet",
    [
        "def handler():\n    pass",
        "@app.get('/items')\ndef items():\n    ...",
        "def save():\n    raise NotImplementedError()",
    ],
)
def test_complete_python_stub_is_only_a_clue(snippet):
    result = classify_evidence(
        {
            "skill": "FastAPI",
            "evidenceList": [
                {
                    "evidenceType": "fastapi_route",
                    "contextComplete": True,
                    "snippet": snippet,
                }
            ],
        },
        "supported",
    )
    assert result["evidence_level"] == 1
    assert "空壳" in result["evidence_level_reason"]


def test_nonempty_function_can_still_reach_task_implementation():
    result = classify_evidence(
        {
            "evidenceList": [
                {
                    "evidenceType": "python_code",
                    "contextComplete": True,
                    "snippet": "def total(values):\n    return sum(values)",
                }
            ]
        },
        "supported",
    )
    assert result["evidence_level"] == 3
