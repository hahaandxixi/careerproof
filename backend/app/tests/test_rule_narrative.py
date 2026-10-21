import hashlib
from copy import deepcopy

import pytest

from app.tools.code_analyzer import FrozenRetrievalSource, ProjectFileSnapshot
from app.tools.evidence_levels import classify_evidence
from app.tools.rule_narrative import MAX_TEXT, VERSION, build_rule_narrative


def source(path, content):
    return FrozenRetrievalSource(
        ProjectFileSnapshot(path, content), hashlib.sha256(content.encode()).hexdigest(),
    )


def evidence(record, **overrides):
    return {
        "file_path": record.file.path, "snippet": record.file.content.rstrip("\n"),
        "content_hash": record.content_hash, "line_start": 1,
        "line_end": len(record.file.content.splitlines()), "evidence_type": "python_code",
        "provenance": "portfolio", **overrides,
    }


def test_runtime_output_is_included_in_uploaded_inventory_without_becoming_evidence():
    record = source("version-a/ledger.py", "def allocate(n):\n    return n\n")
    runtime = [
        source("runtime/README.txt", "notes"),
        source("runtime/http-observations.json", '{"status": 201}'),
        source("runtime/pytest-output.txt", "11 passed"),
    ]
    narrative = build_rule_narrative([evidence(record)], (record, *runtime))
    assert "runtime/pytest-output.txt" in narrative["gap"]
    assert "11 passed" not in narrative["gap"]
    assert "无需重复上传" in narrative["gap"]


def test_observations_locate_real_source_without_certifying_business_or_tests():
    record = source("version-a/ledger.py", (
        "def allocate(n):\n"
        "    assert n > 0\n"
        "    if n > 10:\n"
        "        raise ValueError('limit')\n"
        "    return n\n"
    ))
    uploaded = source("version-a/observations.json", '{"result":"all passed"}')
    narrative = build_rule_narrative([evidence(record)], (record, uploaded))
    assert "version-a/ledger.py 第1—5行" in narrative["reason"]
    assert "allocate" in narrative["reason"] and "条件分支" in narrative["reason"]
    assert "assert断言" in narrative["reason"] and "测试断言" not in narrative["reason"]
    assert "不代表本项全部业务条件已满足" in narrative["reason"]
    assert "observations.json" in narrative["gap"] and "无需重复上传" in narrative["gap"]
    assert "不代表运行成功" in narrative["gap"]
    assert "all passed" not in narrative["gap"]


@pytest.mark.parametrize("overrides", [
    {"provenance": "reference"}, {"evidence_type": "retrieved_context"},
    {"snippet": "forged"}, {"content_hash": "bad"}, {"line_end": 100},
])
def test_unverified_candidate_or_reference_cannot_become_a_source_observation(overrides):
    record = source("a.py", "def allocate(n):\n    return n\n")
    assert build_rule_narrative([evidence(record, **overrides)], (record,)) is None
    assert build_rule_narrative([evidence(record)], ()) is None


def test_literals_and_comments_do_not_become_observed_calls_or_branches():
    record = source("a.py", (
        "def example():\n"
        "    # if done: connection.rollback()\n"
        "    return 'UPDATE things SET value=1; connection.commit()'\n"
    ))
    reason = build_rule_narrative([evidence(record)], (record,))["reason"]
    assert "SQL调用" not in reason and "commit调用" not in reason and "条件分支" not in reason


def test_source_versions_stay_distinct_and_outputs_are_bounded():
    records = tuple(
        source(f"v{n}/a.py", f"def allocate_{n}(n):\n    return n\n") for n in range(15)
    )
    narrative = build_rule_narrative([evidence(record) for record in records], records)
    assert all(f"v{n}/a.py" in narrative["reason"] for n in range(3))
    assert "v3/a.py" not in narrative["reason"]
    assert max(len(narrative["reason"]), len(narrative["gap"])) <= MAX_TEXT


def test_incomplete_python_does_not_invent_structure():
    record = source("partial.py", "    if value:\n")
    reason = build_rule_narrative([evidence(record)], (record,))["reason"]
    assert "局部源码，结构尚未确认" in reason


def snapshot():
    return {"skill": "Python", "ruleClassificationVersion": "practice-evidence-v5-redis-operation",
            "evidenceList": [{"evidenceType": "python_code", "contextComplete": True,
                              "snippet": "def allocate(n):\n    return n"}]}


def test_saved_new_guidance_changes_only_text_and_old_snapshot_is_unchanged():
    legacy = snapshot()
    before = deepcopy(legacy)
    old = classify_evidence(legacy, "supported")
    new = classify_evidence({**legacy, "ruleNarrative": {
        "version": VERSION, "reason": "定位到原文及边界", "gap": "核对现有记录，仅补未覆盖场景",
    }}, "supported")
    assert {key: value for key, value in new.items() if key not in {
        "evidence_level_reason", "evidence_level_gap",
    }} == {key: value for key, value in old.items() if key not in {
        "evidence_level_reason", "evidence_level_gap",
    }}
    assert new["evidence_level_gap"] == "核对现有记录，仅补未覆盖场景"
    assert legacy == before and classify_evidence(legacy, "supported") == old


@pytest.mark.parametrize("review", ["rejected", "corrected"])
def test_frozen_rule_text_cannot_hide_a_review_rejection(review):
    original = snapshot()
    marked = {**original, "ruleNarrative": {"version": VERSION, "reason": "new", "gap": "new"}}
    assert classify_evidence(marked, "supported", review) == classify_evidence(
        original, "supported", review,
    )


def test_unsupported_and_validated_ai_remain_authoritative():
    original = snapshot()
    marker = {"version": VERSION, "reason": "new", "gap": "new"}
    assert classify_evidence({**original, "ruleNarrative": marker}, "unsupported") == (
        classify_evidence(original, "unsupported")
    )
    original["ai"] = {"status": "validated", "informationGap": "模型原缺口", "rating": {
        "level": None, "reason": "相关性尚未确认", "criteria": [],
    }}
    # Invalid AI records are not used as a counterfeit positive result either.
    from app.agents.contracts import AIRating
    original["ai"]["rating"] = AIRating(level=None, reason="相关性尚未确认", criteria=[
        {"criterion": criterion, "supported": False, "reason": "尚未确认"}
        for criterion in ("relevance", "operation", "task")
    ]).model_dump()
    assert classify_evidence({**original, "ruleNarrative": marker}, "supported") == (
        classify_evidence(original, "supported")
    )
