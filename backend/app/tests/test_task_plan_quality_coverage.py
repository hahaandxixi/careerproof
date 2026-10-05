"""Coverage regressions for the six named gap kinds in task-plan offline probes.

Offline only: authored fixtures, no provider, no network, no database, no browser.
"""

from evals.run_task_plan_quality import (
    case_context,
    case_files,
    draft_probe,
    evaluate,
    load_cases,
    suite_exit_ok,
    validate_output,
)

DEFAULT_CASES = load_cases()

LEGACY_CASE_IDS = {
    "fastapi-health-execution",
    "python-sum-runtime",
    "postgres-query-execution",
    "pytest-regression",
    "content-operations-review",
    "event-planning-budget",
    "docker-service-start",
    "redis-unimplemented-first",
    "python-claim-review",
}
LEGACY_NEGATIVE_PROBES = {
    ("fastapi-health-execution", "repeat-source"),
    ("python-sum-runtime", "repeat-source"),
    ("redis-unimplemented-first", "runtime-without-implementation"),
    ("python-claim-review", "repeat-source"),
}
SIX_GAP_KINDS = {
    "implementation",
    "partial-implementation",
    "missing-run",
    "unclear-contribution",
    "contradictory-materials",
    "reference-only",
}
# The four negative probes that were registered as red lights when the contract
# could not reject them (independent audit evidence preserved under
# docs/evidence/20261005-AI-codex-audit/). Codex's task_boundaries contract fix
# now rejects them, so this regression asserts actual rejection and a green
# suite — the historical red-light evidence itself stays untouched.
FORMER_REGISTERED_SEMANTIC_GAPS = {
    ("python-cache-partial", "partial-as-complete"),
    ("group-project-boundary", "group-artifact-as-personal"),
    ("conflicting-export-materials", "silent-pick-one-side"),
    ("reference-only-sql", "reference-as-personal-practice"),
}


def _case(case_id: str) -> dict:
    return next(case for case in DEFAULT_CASES if case["id"] == case_id)


def test_legacy_cases_and_probes_preserved() -> None:
    by_id = {case["id"]: case for case in DEFAULT_CASES}
    assert set(by_id) >= LEGACY_CASE_IDS
    for case_id, probe_id in LEGACY_NEGATIVE_PROBES:
        negatives = by_id[case_id]["knownBadDrafts"]
        assert any(
            row["id"] == probe_id and row["expectedContractRejection"]
            for row in negatives
        ), (case_id, probe_id)


def test_six_gap_kinds_have_authored_positive_and_negative() -> None:
    by_kind: dict[str, list[dict]] = {}
    for case in DEFAULT_CASES:
        by_kind.setdefault(case["gapKind"], []).append(case)
    assert set(by_kind) >= SIX_GAP_KINDS
    for kind in SIX_GAP_KINDS:
        for case in by_kind[kind]:
            assert case["referenceDraft"], kind
            assert case["knownBadDrafts"], kind


def test_path_collision_and_duplicate_normalized_paths_rejected() -> None:
    base = _case("reference-only-sql")
    collision = {
        **base,
        "id": "synthetic-collision",
        "referenceFiles": [{"path": "notes.md", "content": "SELECT 1;\n"}],
    }
    try:
        case_files(collision)
    except ValueError as error:
        assert "collision" in str(error)
    else:
        raise AssertionError("personal/reference path collision must be rejected")
    duplicate = {
        **base,
        "id": "synthetic-duplicate",
        "referenceFiles": [
            {"path": "vendor.sql", "content": "SELECT 1;\n"},
            {"path": "vendor.sql", "content": "SELECT 2;\n"},
        ],
    }
    try:
        case_files(duplicate)
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate normalized paths must be rejected")


def test_reference_only_case_keeps_personal_verdict_and_provenance() -> None:
    case = _case("reference-only-sql")
    contexts, exact, source_count = case_context(case)
    context = contexts[0]
    # High-strength reference SQL must never raise the personal verdict.
    assert context.verdict in {"claimed_only", "gap"}
    assert source_count > 0 and exact
    provenance = {source.provenance for source in context.evidence}
    assert provenance <= {"portfolio", "reference"}
    assert "reference" in provenance
    personal_paths = {row["path"] for row in case["files"]}
    for source in context.evidence:
        if source.provenance == "reference":
            assert source.file_path not in personal_paths


def test_empty_evidence_reported_separately_and_not_failing() -> None:
    case = {
        "id": "synthetic-empty-evidence",
        "direction": "合成",
        "requirement": "实现 COBOL 批处理作业并保存运行记录",
        "skill": "COBOL",
        "resume": "没有相关材料。",
        "files": [],
        "gapKind": "implementation",
        "qualityRubric": "合成空证据样例，用于锁定零引用统计语义。",
        "referenceDraft": {
            "deliverable": "具名批处理实现",
            "steps": ["补充作业实现"],
            "acceptanceChecks": ["实现可定位"],
        },
        "knownBadDrafts": [],
    }
    report = evaluate([case])
    row = report["results"][0]
    assert row["sourceCheck"] == "no-sources"
    assert row["sourceExact"] is False and row["sourceCount"] == 0
    metrics = report["metrics"]
    assert metrics["noSourceCount"] == 1
    assert metrics["sourceMismatchCount"] == 0
    assert metrics["sourceExactCount"] == 0
    assert suite_exit_ok(report)


def test_replay_does_not_raise_semantic_review_counts() -> None:
    case = _case("reference-only-sql")
    contexts, _, _ = case_context(case)
    probe = draft_probe(contexts[0], case["referenceDraft"])
    replay = {"summary": probe["summary"], "model": "authored-replay-fixture",
              "items": probe["items"]}
    assert validate_output(contexts, replay)["accepted"]
    report = evaluate([case], {case["id"]: replay})
    assert report["mode"] == "saved-output-replay"
    metrics = report["metrics"]
    assert metrics["replayedModelOutputs"] == 1
    assert metrics["independentSemanticReviews"] == 0
    assert metrics["semanticQualityPassRate"] is None
    review = report["results"][0]["independentSemanticReview"]
    assert review["status"] == "pending" and review["reviewer"] is None


def test_missing_run_negative_is_rejected_by_contract() -> None:
    row = evaluate([_case("api-run-record-missing")])["results"][0]
    negative = row["probes"][1]
    assert negative["id"] == "source-as-runtime-proof"
    assert negative["accepted"] is False
    assert negative["contractExpectationMatched"]


def test_former_registered_red_lights_are_now_actually_rejected() -> None:
    report = evaluate([
        _case(case_id)
        for case_id, _ in sorted(FORMER_REGISTERED_SEMANTIC_GAPS)
    ])
    rejected = {
        (row["id"], probe["id"])
        for row in report["results"] for probe in row["probes"][1:]
        if probe["accepted"] is False and probe["contractExpectationMatched"]
    }
    assert rejected >= FORMER_REGISTERED_SEMANTIC_GAPS


def test_boundary_positives_keep_negation_pending_and_future_plans() -> None:
    # The authored reference drafts state the refusal/pending/future boundary
    # explicitly; the contract must keep accepting them (no over-rejection).
    report = evaluate(DEFAULT_CASES)
    by_id = {row["id"]: row for row in report["results"]}
    for case_id, positive in {
        "python-cache-partial": "补充写路径与过期策略的实现步骤及测试计划",
        "group-project-boundary": "列出本人提交的模块文件与对应提交记录",
        "conflicting-export-materials": "将结论状态标记为待核验",
        "reference-only-sql": "不将参考实现计入个人证据",
    }.items():
        probe = by_id[case_id]["probes"][0]
        assert probe["id"] == "authored-reference" and probe["accepted"], case_id
        assert any(
            positive in step for step in probe["draft"]["steps"]
        ) or any(positive in check for check in probe["draft"]["acceptanceChecks"]), case_id
    assert report["metrics"]["referenceContractAccepted"] == len(DEFAULT_CASES)


def test_full_suite_partition_and_contract_expectations_all_matched() -> None:
    report = evaluate(DEFAULT_CASES)
    metrics = report["metrics"]
    assert metrics["caseCount"] == len(DEFAULT_CASES)
    assert metrics["noSourceCount"] + metrics["sourceExactCount"] == metrics["caseCount"]
    assert metrics["sourceMismatchCount"] == 0
    assert report["externalCalls"] == 0
    # Every one of the 23 authored probes must match its case expectation: the
    # four former red lights are now rejections, nothing else drifted.
    assert metrics["contractProbeCount"] == 23
    assert metrics["contractExpectationMatches"] == metrics["contractProbeCount"]
    assert metrics["contractExpectationMismatches"] == []
    assert metrics["independentSemanticReviews"] == 0
    assert metrics["semanticQualityPassRate"] is None
    assert suite_exit_ok(report)
