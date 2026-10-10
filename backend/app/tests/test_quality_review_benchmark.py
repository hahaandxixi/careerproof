"""Targeted tests for the combined offline review benchmark (传智杯28).

Pins the joint-report contract: the frozen 2026-10-10 independent blind
review replays deterministically over the frozen 8-case input, schema
violations are hard failures that can never be masked as unscored, null
scores stay in every denominator, source contradictions cannot be offset
by high other-dimension scores, and author label coverage stays separate
from independent strict pass.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evals import run_quality_dimensions as runner  # noqa: E402
from evals import run_quality_review_benchmark as benchmark  # noqa: E402

FROZEN_INPUT = benchmark.DEFAULT_INPUT
FROZEN_REVIEW = benchmark.DEFAULT_REVIEW
DIMS = benchmark.CANONICAL_DIMS
STRICT_PASS_IDS = ["0f2a863462", "37882b616f", "f5c5e00efe"]
SOURCE_ZERO_IDS = ["09fb4e82f3", "e2fd108ad9"]


def _fixture_pair(case_ids=("c1", "c2"), scores=None):
    """Small injected stand-ins for the frozen input/review JSON schema."""
    input_payload = {
        "kind": "authored-synthetic-drafts-not-website-model-output",
        "rubric": {dim: "说明" for dim in DIMS},
        "cases": [
            {
                "id": cid,
                "requirement": {"title": f"需求{cid}", "skill": "Python", "weight": 5},
                "draft": {
                    "deliverable": "具名交付物", "steps": ["步骤一"],
                    "acceptanceChecks": ["核对项"],
                },
            }
            for cid in case_ids
        ],
    }
    raw = json.dumps(input_payload, ensure_ascii=False).encode("utf-8")
    scores = scores or {cid: dict.fromkeys(DIMS, 2) for cid in case_ids}
    cases = [
        {
            "caseId": cid,
            "requirementTitle": f"需求{cid}",
            "scores": scores[cid],
            "evidence": {
                dim: (f"{dim}理由" if scores[cid].get(dim) is not None else "")
                for dim in DIMS
            },
            "neededSupplements": "需补充点",
        }
        for cid in case_ids
    ]
    review_payload = {
        "reviewer": "独立评审", "model": "model-x", "plan": "plan-x",
        "reviewedAt": "2026-10-11T00:00:00+08:00", "humanReview": False,
        "inputSha256": hashlib.sha256(raw).hexdigest(),
        "cases": cases,
    }
    return input_payload, review_payload, raw


def _validate(input_payload, review_payload, raw):
    return benchmark.validate_blind_review(input_payload, review_payload, raw)


@pytest.fixture(scope="module")
def report():
    return benchmark.build_report()


# --- frozen 8-case replay over the real production three-dimension path ---


def test_frozen_replay_counts_and_strict_pass(report):
    metrics = report["blindReviewReplay"]["metrics"]
    assert metrics["reviewedAuthoredDrafts"] == 8  # noqa: PLR2004
    assert metrics["sampleDenominator"] == 8  # noqa: PLR2004
    assert metrics["strictPass"]["count"] == 3  # noqa: PLR2004
    assert sorted(metrics["strictPass"]["caseIds"]) == STRICT_PASS_IDS
    assert metrics["strictPass"]["rate"] == 0.375
    assert metrics["unscored"]["count"] == 0
    source = metrics["sourceCompliance"]
    assert source["score0"]["count"] == 2  # noqa: PLR2004
    assert sorted(source["score0"]["caseIds"]) == SOURCE_ZERO_IDS
    assert source["score1"]["count"] == 1
    assert source["blockedFromStrictPass"]["count"] == 3  # noqa: PLR2004


def test_frozen_per_dimension_counts_have_full_denominator(report):
    counts = report["blindReviewReplay"]["metrics"]["dimensionCounts"]
    assert counts["sourceCompliance"] == {
        "0": 2, "1": 1, "2": 5, "null": 0, "sampleCount": 8,
    }
    assert counts["stepsExecutable"] == {
        "0": 3, "1": 1, "2": 4, "null": 0, "sampleCount": 8,
    }
    for dim in DIMS:
        assert counts[dim]["sampleCount"] == 8  # noqa: PLR2004
        assert counts[dim]["null"] == 0


def test_frozen_rows_preserve_scores_reasons_supplements(report):
    rows = {row["caseId"]: row for row in report["blindReviewReplay"]["cases"]}
    row = rows["45c8ae3412"]
    assert row["scores"] == {
        "sourceCompliance": 2, "deliverableNamed": 2,
        "stepsExecutable": 1, "checksObservable": 1,
    }
    assert row["reasons"]["stepsExecutable"].startswith("可从第一步")
    assert row["neededSupplements"].startswith("补写路径与失效")
    assert row["strictPass"] is False
    zero = rows["e2fd108ad9"]
    assert zero["scores"]["sourceCompliance"] == 0
    assert any(
        fail["dimension"] == "sourceCompliance" and fail["score"] == 0
        for fail in zero["strictFailReasons"]
    )


def test_metadata_keeps_review_provenance_and_hashes(report):
    metadata = report["metadata"]
    assert metadata["humanReview"] is False
    assert metadata["reviewer"] == "ZCode BigModel GLM-5.3-Flash"
    assert metadata["inputSha256"] == hashlib.sha256(FROZEN_INPUT.read_bytes()).hexdigest()
    assert metadata["reviewSha256"] == hashlib.sha256(FROZEN_REVIEW.read_bytes()).hexdigest()
    assert metadata["structuralSuiteHashes"] == runner.source_hashes()
    assert metadata["benchmarkRunnerSha256"] == hashlib.sha256(
        Path(benchmark.__file__).read_bytes()
    ).hexdigest()


def test_real_production_paths_combined_run(report):
    structural = report["structuralSuite"]
    assert structural["suite"] == "quality-dimensions-v2"
    assert structural["results"]["citation"] and structural["results"]["change"]
    assert structural["metrics"]["suggestion"]["authoredOperabilityCounts"][
        "deliverableNamed"
    ] == {"numerator": 6, "denominator": 6}


def test_author_coverage_stays_separate_from_independent_strict_pass(report):
    metrics = report["metrics"]
    assert metrics["structuralSuitePass"] is True
    assert metrics["blindReviewStrictPass"] == {"count": 3, "rate": 0.375}
    separate = metrics["authoredCoverageSeparate"]
    assert separate["authoredOperabilityCounts"]["deliverableNamed"] == {
        "numerator": 6, "denominator": 6,
    }
    assert separate["independentStrictPassRate"] == 0.375
    assert "不得互相替代" in separate["note"]


def test_website_generation_semantics_stay_null(report):
    metrics = report["metrics"]
    assert metrics["generatedPlanOperabilityRate"] is None
    assert metrics["semanticQualityPassRate"] is None
    assert metrics["generatedWebsiteModelOutputs"] == 0
    assert metrics["humanReview"] is False
    assert report["generatedWebsiteModelOutputs"] == 0
    assert report["externalCalls"] == 0


# --- exit code protocol: poor baseline drafts are data, illegality is fatal ---


def test_exit_ok_despite_low_baseline_strict_pass(report):
    assert report["blindReviewReplay"]["metrics"]["strictPass"]["count"] == 3
    assert benchmark.benchmark_exit_ok(report) is True


def test_structural_suite_failure_makes_exit_nonzero(report):
    broken = copy.deepcopy(report)
    broken["structuralSuite"]["metrics"]["citation"]["failures"].append(
        {"caseId": "injected", "reason": "simulated gold mismatch"}
    )
    assert benchmark.benchmark_exit_ok(broken) is False


def test_illegal_review_evidence_makes_exit_nonzero(report):
    broken = copy.deepcopy(report)
    broken["blindReviewReplay"]["evidenceLegal"] = False
    assert benchmark.benchmark_exit_ok(broken) is False


# --- schema validation on injected stand-in fixtures ---


def test_input_hash_mismatch_rejected():
    input_payload, review_payload, raw = _fixture_pair()
    review_payload["inputSha256"] = "0" * 64
    with pytest.raises(ValueError, match="inputSha256"):
        _validate(input_payload, review_payload, raw)


def test_missing_case_rejected_as_set_incomplete():
    input_payload, review_payload, raw = _fixture_pair()
    review_payload["cases"] = review_payload["cases"][:1]
    with pytest.raises(ValueError, match="case id sets differ"):
        _validate(input_payload, review_payload, raw)


def test_duplicate_case_ids_rejected():
    input_payload, review_payload, raw = _fixture_pair()
    review_payload["cases"].append(copy.deepcopy(review_payload["cases"][0]))
    with pytest.raises(ValueError, match="unique"):
        _validate(input_payload, review_payload, raw)


def test_empty_case_id_rejected():
    input_payload, review_payload, raw = _fixture_pair()
    review_payload["cases"][0]["caseId"] = ""
    with pytest.raises(ValueError, match="nonempty"):
        _validate(input_payload, review_payload, raw)


@pytest.mark.parametrize("bad", [True, False, "2", 2.0, float("nan"), 3])
def test_illegal_score_values_rejected(bad):
    input_payload, review_payload, raw = _fixture_pair()
    review_payload["cases"][0]["scores"]["deliverableNamed"] = bad
    with pytest.raises(ValueError, match="int 0/1/2 or null|outside 0/1/2"):
        _validate(input_payload, review_payload, raw)


def test_missing_dimension_rejected():
    input_payload, review_payload, raw = _fixture_pair()
    del review_payload["cases"][0]["scores"]["checksObservable"]
    with pytest.raises(ValueError, match="missing dimension"):
        _validate(input_payload, review_payload, raw)


@pytest.mark.parametrize("mode", ["key-absent", "empty", "blank"])
def test_missing_reason_is_hard_failure_not_success(mode):
    input_payload, review_payload, raw = _fixture_pair()
    evidence = review_payload["cases"][0]["evidence"]
    if mode == "key-absent":
        del evidence["stepsExecutable"]
    elif mode == "empty":
        evidence["stepsExecutable"] = ""
    else:
        evidence["stepsExecutable"] = "   "
    with pytest.raises(ValueError, match="nonempty text reason"):
        _validate(input_payload, review_payload, raw)


def test_null_score_stays_in_denominator_and_marks_unscored():
    scores = {
        "c1": dict.fromkeys(DIMS, 2),
        "c2": {**dict.fromkeys(DIMS, 2), "stepsExecutable": None},
    }
    input_payload, review_payload, raw = _fixture_pair(scores=scores)
    rows, _, dims = _validate(input_payload, review_payload, raw)
    metrics = benchmark.replay_metrics(rows, dims)
    assert metrics["reviewedAuthoredDrafts"] == 2  # noqa: PLR2004
    assert metrics["sampleDenominator"] == 2  # noqa: PLR2004
    assert metrics["unscored"]["caseIds"] == ["c2"]
    assert metrics["strictPass"]["count"] == 1
    assert metrics["strictPass"]["rate"] == 0.5
    assert metrics["dimensionCounts"]["stepsExecutable"]["null"] == 1
    assert rows[1]["strictPass"] is False and rows[1]["unscored"] is True


def test_source_contradiction_not_offset_by_high_scores():
    scores = {
        "c1": {**dict.fromkeys(DIMS, 2), "sourceCompliance": 0},
        "c2": dict.fromkeys(DIMS, 2),
    }
    input_payload, review_payload, raw = _fixture_pair(scores=scores)
    rows, _, dims = _validate(input_payload, review_payload, raw)
    metrics = benchmark.replay_metrics(rows, dims)
    assert metrics["strictPass"]["count"] == 1
    assert metrics["strictPass"]["caseIds"] == ["c2"]
    assert metrics["sourceCompliance"]["blockedFromStrictPass"]["caseIds"] == ["c1"]
    fail = rows[0]["strictFailReasons"][0]
    assert fail["dimension"] == "sourceCompliance" and fail["score"] == 0


def test_human_review_true_rejected_for_blind_protocol():
    input_payload, review_payload, raw = _fixture_pair()
    review_payload["humanReview"] = True
    with pytest.raises(ValueError, match="humanReview"):
        _validate(input_payload, review_payload, raw)


def test_missing_review_metadata_rejected():
    input_payload, review_payload, raw = _fixture_pair()
    del review_payload["reviewer"]
    with pytest.raises(ValueError, match="reviewer"):
        _validate(input_payload, review_payload, raw)


def test_duplicate_json_keys_rejected_at_any_level(tmp_path):
    payloads = [
        b'{"kind": "authored-synthetic-drafts-not-website-model-output", '
        b'"kind": "x", "rubric": {}, "cases": []}',
        b'{"cases": [{"caseId": "c1", "scores": '
        b'{"sourceCompliance": 0, "sourceCompliance": 2}}]}',
    ]
    for text in payloads:
        path = tmp_path / "dup.json"
        path.write_bytes(text)
        with pytest.raises(ValueError, match="duplicate JSON key"):
            benchmark._read_json(path)


def test_rubric_dimension_reduction_and_extension_rejected():
    mutations = (
        lambda payload: payload["rubric"].pop("stepsExecutable"),
        lambda payload: payload["rubric"].update({"extraDim": "说明"}),
    )
    for mutate in mutations:
        input_payload, review_payload, raw = _fixture_pair()
        mutate(input_payload)
        with pytest.raises(ValueError, match="four canonical dimensions"):
            _validate(input_payload, review_payload, raw)


def test_input_kind_restricted_to_this_protocol():
    input_payload, review_payload, raw = _fixture_pair()
    input_payload["kind"] = "some-other-protocol"
    with pytest.raises(ValueError, match="kind"):
        _validate(input_payload, review_payload, raw)


# --- CLI behaviour ---


def test_cli_rejects_overwrite(tmp_path):
    output = tmp_path / "report.json"
    output.write_text("existing baseline", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        benchmark.main(argv=["--output", str(output)])
    assert excinfo.value.code == 2


def test_cli_invalid_review_returns_1_without_output(tmp_path):
    input_payload, review_payload, _ = _fixture_pair()
    review_payload["inputSha256"] = "1" * 64
    bad_input = tmp_path / "input.json"
    bad_review = tmp_path / "review.json"
    bad_input.write_text(json.dumps(input_payload, ensure_ascii=False), encoding="utf-8")
    bad_review.write_text(json.dumps(review_payload, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "report.json"
    code = benchmark.main(argv=[
        "--input", str(bad_input), "--review", str(bad_review),
        "--output", str(output),
    ])
    assert code == 1
    assert not output.exists()


def test_repeat_reports_identical_except_timestamp():
    first = benchmark.build_report()
    second = benchmark.build_report()
    assert first["structuralSuite"]["generatedAt"] == first["generatedAt"]
    assert second["structuralSuite"]["generatedAt"] == second["generatedAt"]
    for payload in (first, second):
        payload.pop("generatedAt")
        payload["structuralSuite"].pop("generatedAt")
    assert first == second
