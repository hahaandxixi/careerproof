import pytest

from app.tools.evidence_levels import _rule_classification, classify_evidence


def test_empty_and_unsupported_are_not_level_one():
    assert classify_evidence({}, "gap")["evidence_level"] is None
    assert classify_evidence({"claimed": True}, "unsupported")["evidence_level"] is None
    assert classify_evidence({"claimed": True}, "claimed_only")["evidence_level"] is None


@pytest.mark.parametrize("kind", ["semantic_document_candidate", "retrieved_context"])
def test_retrieval_candidates_do_not_raise_a_rule_fallback_level(kind):
    snapshot = {"skill": "Redis", "claimed": True, "evidenceList": [
        {"evidenceType": kind, "snippet": "待执行：保存函数输入输出", "contextComplete": True},
    ]}
    result = classify_evidence(snapshot, "claimed_only")
    assert result["evidence_level"] is None
    assert result["evidence_level_label"] == "待核对检索候选"
    ceiling = _rule_classification(snapshot, "claimed_only", include_candidates=True)
    assert ceiling["evidence_level"] == 1


def test_validated_ai_relevance_can_use_a_candidate_without_implying_operation():
    snapshot = {
        "skill": "活动策划", "evidenceList": [{"evidenceType": "semantic_document_candidate"}],
        "ai": {"status": "validated", "rating": {
            "level": 1, "reason": "文档有待核对的相关计划线索",
            "criteria": [
                {"criterion": "relevance", "supported": True,
                 "citation_ids": ["R1-E1"], "reason": "计划与活动要求相关"},
                {"criterion": "operation", "supported": False, "reason": "未展示具体操作"},
                {"criterion": "task", "supported": False, "reason": "未展示完整过程"},
            ],
        }},
    }
    assert classify_evidence(snapshot, "claimed_only")["evidence_level"] == 1
    assert classify_evidence(snapshot, "claimed_only")["evidence_level_source"] == "ai_preliminary"
    snapshot["ai"]["status"] = "fallback"
    assert classify_evidence(snapshot, "claimed_only")["evidence_level"] is None


def test_candidates_do_not_hide_a_direct_dependency_or_implementation():
    snapshot = {"evidenceList": [
        {"evidenceType": "retrieved_context"}, {"evidenceType": "dependency"},
    ]}
    assert classify_evidence(snapshot, "partial")["evidence_level"] == 1
    snapshot["evidenceList"][1] = {"evidenceType": "python_code", "contextComplete": True}
    assert classify_evidence(snapshot, "supported")["evidence_level"] == 3


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
