"""Targeted tests for the offline three-dimension quality evaluation suite.

The suite replays authored synthetic inputs and frozen golden labels through
production paths only. These tests pin the contract the evidence task card
relies on: labels are authored (never model output), every gold expectation
matches production behaviour, no-source cases stay out of citation success,
runs are repeatable, and case filtering is strict.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evals import run_quality_dimensions as runner  # noqa: E402

REQUIRED_GAP_CATEGORIES = {
    "run-record", "implementation-gap", "partial-implementation",
    "ownership-gap", "data-review", "reference-substitution",
}
REQUIRED_CHANGE_GROUPS = {
    "no-change", "materials-only", "requirements-only", "both-changed",
    "evidence-deleted", "provenance-role", "same-path-diff-hash",
    "citation-id-reuse", "old-citation-out-of-bounds",
}


@pytest.fixture(scope="module")
def cases() -> dict:
    return runner.load_cases()


@pytest.fixture(scope="module")
def report(cases) -> dict:
    return runner.evaluate(cases)


def test_fixture_is_frozen_authored_labels(cases):
    ids = [
        row["id"] for row in [
            *cases["citationCases"], *cases["suggestionCases"],
            *cases["changeCases"],
        ]
    ]
    assert len(ids) == len(set(ids)) and len(ids) == 23
    assert "作者合成标签" in cases["labelAuthorship"]
    assert "不是真实模型输出" in cases["labelAuthorship"]
    assert set(cases["gapCategoryMapping"]) == REQUIRED_GAP_CATEGORIES
    assert set(cases["changeGroupRationale"]) == REQUIRED_CHANGE_GROUPS


def test_citation_dimension_matches_gold(report):
    metrics = report["metrics"]["citation"]
    assert metrics["sourceMismatchCount"] == 0
    assert metrics["failures"] == []
    assert metrics["validCitationAcceptanceRate"] == 1.0
    assert metrics["outOfBoundsRejectionRate"] == 1.0


def test_no_source_case_is_separate_never_citation_success(report):
    metrics = report["metrics"]["citation"]
    assert metrics["noSourceCount"] == 1
    assert metrics["noSourceCaseIds"] == ["cit-no-source-downgrade"]
    assert "cit-no-source-downgrade" not in metrics["sourcedCaseIds"]
    # 7 sourced cases carry 2 gold-accept and 5 gold-reject drafts; the
    # no-source case's gold-accept draft stays out of both numerators.
    assert metrics["draftsTotal"] == 8  # noqa: PLR2004
    assert metrics["validCitationGoldAccept"] == 2  # noqa: PLR2004
    assert metrics["outOfBoundsGoldReject"] == 5  # noqa: PLR2004


def test_suggestion_dimension_matches_gold(report):
    metrics = report["metrics"]["suggestion"]
    assert set(metrics["gapCategoryCoverage"]) == REQUIRED_GAP_CATEGORIES
    assert metrics["failures"] == []
    assert metrics["expectationMatches"] == metrics["probesTotal"]
    assert metrics["referenceDraftAccepted"] == metrics["referenceDraftTotal"] == 6
    assert metrics["badDraftRejectionRate"] == 1.0
    assert metrics["operabilityCounts"] is None
    assert metrics["generatedPlanOperabilityRate"] is None
    for field in ("deliverableNamed", "stepsExecutable", "checksObservable"):
        assert metrics["authoredOperabilityCounts"][field] == {"numerator": 6, "denominator": 6}


def test_change_dimension_matches_gold(report):
    metrics = report["metrics"]["change"]
    assert set(metrics["changeGroupCoverage"]) == REQUIRED_CHANGE_GROUPS
    assert metrics["failures"] == []
    assert metrics["changeTypeAccuracy"] == 1.0
    assert metrics["attributionSignalRate"] == 1.0
    assert metrics["remainingGapIdentificationRate"] == 1.0


def test_semantic_quality_stays_null_without_independent_review(report):
    metrics = report["metrics"]
    assert metrics["semanticQualityPassRate"] is None
    assert metrics["independentSemanticReviews"] == 0
    assert report["syntheticDataOnly"] is True
    assert report["externalCalls"] == 0


def test_old_citation_replay_is_rejected(report):
    row = next(
        item for item in report["results"]["change"]
        if item["id"] == "chg-old-citation-out-of-bounds"
    )
    replay = row["oldCitationReplay"]
    assert replay["accepted"] is False
    assert len(replay["oldCitationIds"]) == 2  # noqa: PLR2004 两个旧要求都被重放
    assert len(replay["newRequirementIds"]) == 1


def test_runs_are_repeatable_except_timestamp(cases):
    first = runner.evaluate(cases)
    second = runner.evaluate(cases)
    first.pop("generatedAt")
    second.pop("generatedAt")
    assert first == second


def test_case_selection_filters_and_rejects_unknown_ids(cases):
    selected = runner.select(cases, {"cit-valid-personal", "chg-no-change"})
    assert [row["id"] for row in selected["citationCases"]] == ["cit-valid-personal"]
    assert selected["suggestionCases"] == []
    assert [row["id"] for row in selected["changeCases"]] == ["chg-no-change"]
    with pytest.raises(ValueError, match="unknown case ids"):
        runner.select(cases, {"no-such-case"})


def test_suite_exit_ok_reflects_all_gold_matches(report):
    assert runner.suite_exit_ok(report) is True
