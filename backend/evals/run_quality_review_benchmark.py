"""Combined offline review benchmark: structural three-dimension suite plus
the frozen independent blind-review replay (传智杯28).

The structural half delegates entirely to evals.run_quality_dimensions
(load_cases/evaluate) — production logic is never copied. The blind-review
half is a deterministic replay of the frozen 2026-10-10 independent model
scores over the frozen 8-case input: it re-validates the evidence chain
(duplicate-key-free JSON, protocol kind, exact four-dimension rubric, input
SHA256, case-id set equality, score schema, per-score reasons) and
recomputes the strict-pass baseline, but never re-scores with a model and
never proves anything about real website generation.

Honesty invariants pinned by tests: the result is called
reviewedAuthoredDrafts, never website real generation; every sample stays
in the denominators and null scores are counted separately as unscored;
a sourceCompliance of 0/1/null fails or leaves the case unscored no matter
how high the other dimensions are; author label coverage is reported next
to — never merged with — the independent strict pass; generatedPlan
OperabilityRate and semanticQualityPassRate stay null; humanReview is false.
A structurally passing suite with low blind-review strict passes exits 0
(the frozen baseline really contains poor drafts); illegal input/score
evidence or structural suite failures exit non-zero and never masquerade
as unscored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from evals import run_quality_dimensions

SUITE = "quality-review-benchmark-v1"
CANONICAL_DIMS = (
    "sourceCompliance", "deliverableNamed", "stepsExecutable", "checksObservable",
)
REQUIRED_INPUT_KIND = "authored-synthetic-drafts-not-website-model-output"
VALID_SCORES = (0, 1, 2)
DEFAULT_INPUT = Path(__file__).with_name("quality-blind-plan-review-input.json")
DEFAULT_REVIEW = (
    Path(__file__).resolve().parents[2]
    / "docs" / "evidence" / "20261010-AI-blind-plan-review" / "review.json"
)
AUTHOR_VS_REVIEW_NOTE = (
    "作者标签覆盖率（结构suite authoredOperabilityCounts）只证明作者声明齐全，"
    "不证明建议实际可执行；与独立盲评严格通过分列，不得互相替代。"
)
REPLAY_NOTE = (
    "对既有独立模型评分（2026-10-10 冻结 review）的确定性回放：不重新调用模型、"
    "不重新评分，也不是人工证明；评分代表作者合成草稿质量基线，"
    "不代表网站真实生成建议的质量。"
)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reject_duplicate_keys(pairs):
    """object_pairs_hook: duplicate keys at any object level are evidence
    tampering (json.loads would silently keep the last value), so reject."""
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key: {key!r}")
        seen[key] = value
    return seen


def _read_json(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
        )
    except ValueError as error:
        raise ValueError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return payload, raw


def _score_error(where: str, value) -> str:
    kind = type(value).__name__
    return f"{where}: score must be int 0/1/2 or null, got {kind} ({value!r})"


def validate_blind_review(
    input_payload: dict, review_payload: dict, input_raw: bytes,
) -> tuple[list[dict], dict, list[str]]:
    """Validate the frozen input/review evidence chain; raise ValueError on
    any illegality. Returns (per-case rows, review metadata, dimensions)."""
    kind = input_payload.get("kind")
    if kind != REQUIRED_INPUT_KIND:
        raise ValueError(
            f"input kind must be {REQUIRED_INPUT_KIND!r}, got {kind!r}"
        )
    rubric = input_payload.get("rubric")
    if not isinstance(rubric, dict) or set(rubric) != set(CANONICAL_DIMS):
        observed = sorted(rubric) if isinstance(rubric, dict) else rubric
        raise ValueError(
            "input rubric must define exactly the four canonical dimensions "
            f"{sorted(CANONICAL_DIMS)}, got {observed!r}"
        )
    dims = list(CANONICAL_DIMS)

    claimed = review_payload.get("inputSha256")
    actual = _sha256_bytes(input_raw)
    if not isinstance(claimed, str) or claimed != actual:
        raise ValueError(
            f"review.inputSha256 {claimed!r} does not match input bytes sha256 {actual}"
        )
    metadata = {}
    for field in ("reviewer", "model", "plan", "reviewedAt"):
        value = review_payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"review.{field} must be a nonempty string, got {value!r}")
        metadata[field] = value
    if review_payload.get("humanReview") is not False:
        raise ValueError(
            "review.humanReview must be exactly false for the independent "
            "blind-review protocol"
        )
    metadata["humanReview"] = False

    input_cases = input_payload.get("cases")
    review_cases = review_payload.get("cases")
    if not isinstance(input_cases, list) or not input_cases:
        raise ValueError("input cases must be a nonempty list")
    if not isinstance(review_cases, list) or not review_cases:
        raise ValueError("review cases must be a nonempty list")
    input_ids = [case.get("id") for case in input_cases]
    if any(not isinstance(cid, str) or not cid.strip() for cid in input_ids):
        raise ValueError("input case ids must be nonempty strings")
    if len(input_ids) != len(set(input_ids)):
        raise ValueError("input case ids must be unique")
    for case in review_cases:
        if not isinstance(case, dict):
            raise ValueError("each review case must be an object")
    review_ids = [case.get("caseId") for case in review_cases]
    if any(not isinstance(cid, str) or not cid.strip() for cid in review_ids):
        raise ValueError("review caseId must be a nonempty string")
    if len(review_ids) != len(set(review_ids)):
        raise ValueError("review caseIds must be unique")
    input_only = sorted(set(input_ids) - set(review_ids))
    review_only = sorted(set(review_ids) - set(input_ids))
    if input_only or review_only:
        raise ValueError(
            f"case id sets differ: review-only={review_only}, input-only={input_only}"
        )

    input_by_id = dict(zip(input_ids, input_cases, strict=True))
    rows = []
    for case in review_cases:
        cid = case["caseId"]
        input_case = input_by_id[cid]
        scores_raw = case.get("scores")
        if not isinstance(scores_raw, dict):
            raise ValueError(f"case {cid}: scores must be an object")
        missing = [dim for dim in dims if dim not in scores_raw]
        if missing:
            raise ValueError(f"case {cid}: missing dimension scores: {missing}")
        extra = [dim for dim in scores_raw if dim not in dims]
        if extra:
            raise ValueError(f"case {cid}: unknown dimension scores: {extra}")
        evidence = case.get("evidence")
        if evidence is not None and not isinstance(evidence, dict):
            raise ValueError(f"case {cid}: evidence must be an object when present")
        scores: dict[str, int | None] = {}
        reasons: dict[str, str | None] = {}
        for dim in dims:
            where = f"case {cid} dimension {dim}"
            value = scores_raw[dim]
            if value is None:
                scores[dim] = None
                text = evidence.get(dim) if isinstance(evidence, dict) else None
                reasons[dim] = text.strip() if isinstance(text, str) else None
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(_score_error(where, value))
            if value not in VALID_SCORES:
                raise ValueError(f"{where}: score {value} outside 0/1/2")
            scores[dim] = value
            text = evidence.get(dim) if isinstance(evidence, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"{where}: non-null score requires a nonempty text reason"
                )
            reasons[dim] = text
        strict_pass = all(
            scores[dim] == 2 and reasons[dim] and reasons[dim].strip() for dim in dims
        )
        fail_reasons = []
        for dim in dims:
            score = scores[dim]
            if score is None:
                fail_reasons.append({"dimension": dim, "score": None, "kind": "unscored"})
            elif dim == "sourceCompliance" and score != 2:
                fail_reasons.append({
                    "dimension": dim, "score": score,
                    "kind": "source-contradiction-or-missing-bound",
                })
            elif score != 2:
                fail_reasons.append({"dimension": dim, "score": score, "kind": "below-strict"})
        requirement = input_case.get("requirement")
        rows.append({
            "caseId": cid,
            "requirementTitle": (
                requirement.get("title") if isinstance(requirement, dict) else None
            ) or case.get("requirementTitle"),
            "draft": input_case.get("draft"),
            "scores": scores,
            "reasons": reasons,
            "neededSupplements": case.get("neededSupplements"),
            "unscored": any(score is None for score in scores.values()),
            "strictPass": strict_pass,
            "strictFailReasons": fail_reasons,
        })
    return rows, metadata, dims


def replay_metrics(rows: list[dict], dims: list[str]) -> dict:
    """Strict-pass baseline over ALL rows; nulls are unscored, never removed."""
    total = len(rows)
    strict_ids = [row["caseId"] for row in rows if row["strictPass"]]
    unscored_ids = [row["caseId"] for row in rows if row["unscored"]]
    dimension_counts = {
        dim: {
            "0": sum(row["scores"][dim] == 0 for row in rows),
            "1": sum(row["scores"][dim] == 1 for row in rows),
            "2": sum(row["scores"][dim] == 2 for row in rows),
            "null": sum(row["scores"][dim] is None for row in rows),
            "sampleCount": total,
        }
        for dim in dims
    }
    metrics = {
        "reviewedAuthoredDrafts": total,
        "sampleDenominator": total,
        "dims": dims,
        "dimensionCounts": dimension_counts,
        "strictPass": {
            "count": len(strict_ids),
            "rate": round(len(strict_ids) / total, 4) if total else None,
            "caseIds": strict_ids,
        },
        "strictFail": {
            "count": total - len(strict_ids),
            "caseIds": [row["caseId"] for row in rows if not row["strictPass"]],
            "note": (
                "四维全为2且均有理由才算严格通过；来源0/1/未评分直接不通过或未评分，"
                "其他高分不能抵消。"
            ),
        },
        "unscored": {
            "count": len(unscored_ids),
            "caseIds": unscored_ids,
            "note": "null独立计unscored，保留在全部分母中，不剔出后抬高成功率。",
        },
    }
    if "sourceCompliance" in dims:
        def _ids(score):
            return [row["caseId"] for row in rows if row["scores"]["sourceCompliance"] == score]

        blocked = [row["caseId"] for row in rows if row["scores"]["sourceCompliance"] != 2]
        metrics["sourceCompliance"] = {
            "score0": {"count": len(_ids(0)), "caseIds": _ids(0)},
            "score1": {"count": len(_ids(1)), "caseIds": _ids(1)},
            "null": {"count": len(_ids(None)), "caseIds": _ids(None)},
            "blockedFromStrictPass": {"count": len(blocked), "caseIds": blocked},
            "note": "sourceCompliance 0=越界或与来源矛盾，1=缺少边界；不为2即不严格通过。",
        }
    return metrics


def build_report(
    input_path: Path = DEFAULT_INPUT,
    review_path: Path = DEFAULT_REVIEW,
    cases_path: Path | None = None,
) -> dict:
    """Validate the blind-review evidence, replay it, and run the production
    structural suite; assemble the joint report with both verdicts separate."""
    generated_at = datetime.now(UTC).isoformat()
    cases_path = cases_path or run_quality_dimensions.DEFAULT_CASES
    input_payload, input_raw = _read_json(input_path)
    review_payload, review_raw = _read_json(review_path)
    rows, review_metadata, dims = validate_blind_review(
        input_payload, review_payload, input_raw,
    )
    metrics = replay_metrics(rows, dims)

    cases = run_quality_dimensions.load_cases(cases_path)
    structural = run_quality_dimensions.evaluate(cases, fixture_path=cases_path)
    structural["generatedAt"] = generated_at

    suggestion_metrics = structural["metrics"]["suggestion"]
    report = {
        "suite": SUITE,
        "generatedAt": generated_at,
        "syntheticDataOnly": True,
        "externalCalls": 0,
        "generatedWebsiteModelOutputs": 0,
        "humanReview": False,
        "replayNature": REPLAY_NOTE,
        "scope": (
            "结构/契约指标（三维suite）与独立盲评草稿质量基线分列；"
            "结构过线不等于草稿质量通过。"
        ),
        "metadata": {
            **review_metadata,
            "inputPath": str(input_path),
            "reviewPath": str(review_path),
            "inputSha256": _sha256_bytes(input_raw),
            "reviewSha256": _sha256_bytes(review_raw),
            "benchmarkRunnerSha256": _sha256_bytes(Path(__file__).read_bytes()),
            "structuralSuiteHashes": structural["sourceHashes"],
        },
        "structuralSuite": structural,
        "blindReviewReplay": {
            "nature": REPLAY_NOTE,
            "dims": dims,
            "cases": rows,
            "metrics": metrics,
            "replayComplete": len(rows) == len(input_payload["cases"]),
            "evidenceLegal": True,
        },
        "metrics": {
            "structuralSuitePass": run_quality_dimensions.suite_exit_ok(structural),
            "blindReviewEvidenceLegal": True,
            "blindReviewReplayComplete": len(rows) == len(input_payload["cases"]),
            "reviewedAuthoredDrafts": metrics["reviewedAuthoredDrafts"],
            "blindReviewStrictPass": {
                "count": metrics["strictPass"]["count"],
                "rate": metrics["strictPass"]["rate"],
            },
            "authoredCoverageSeparate": {
                "authoredOperabilityCounts": suggestion_metrics[
                    "authoredOperabilityCounts"
                ],
                "independentStrictPassRate": metrics["strictPass"]["rate"],
                "note": AUTHOR_VS_REVIEW_NOTE,
            },
            "generatedWebsiteModelOutputs": 0,
            "humanReview": False,
            "generatedPlanOperabilityRate": None,
            "semanticQualityPassRate": None,
        },
    }
    return report


def benchmark_exit_ok(report: dict) -> bool:
    """Illegal evidence or a failing structural suite must exit non-zero;
    a low strict-pass baseline on the frozen authored drafts is expected
    data and must not fail the run. The structural verdict is recomputed
    from the embedded suite, never from a cached flag."""
    return (
        report["blindReviewReplay"]["evidenceLegal"] is True
        and report["blindReviewReplay"]["replayComplete"] is True
        and run_quality_dimensions.suite_exit_ok(report["structuralSuite"])
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(
            "Output already exists; choose a new filename to preserve baselines"
        )
    try:
        report = build_report(
            input_path=args.input, review_path=args.review, cases_path=args.cases,
        )
    except ValueError as error:
        print(f"benchmark input invalid: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    summary = {
        "structuralSuitePass": report["metrics"]["structuralSuitePass"],
        "reviewedAuthoredDrafts": report["metrics"]["reviewedAuthoredDrafts"],
        "blindReviewStrictPass": report["metrics"]["blindReviewStrictPass"],
        "blindReviewUnscored": report["blindReviewReplay"]["metrics"]["unscored"][
            "count"
        ],
        "generatedPlanOperabilityRate": None,
        "semanticQualityPassRate": None,
        "exitOk": benchmark_exit_ok(report),
    }
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if benchmark_exit_ok(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
