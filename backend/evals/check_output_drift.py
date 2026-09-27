"""Compare frozen synthetic evaluations; paid execution requires two explicit flags."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def ordered_records(records, identity):
    """A model output array is keyed by identity, not presentation order."""
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("Evaluation records must be a list of objects")
    seen = set()
    for row in records:
        key = row.get(identity)
        if not isinstance(key, str) or not key.strip() or key in seen:
            raise ValueError(f"Missing, invalid or duplicated {identity}")
        seen.add(key)
    return sorted(records, key=lambda row: row[identity])


def signals(row):
    analysis = row.get("analysis") or {}
    items = ordered_records(analysis.get("items", []), "requirement_id")
    return {
        "accepted": row.get("accepted"),
        "citationLegal": row.get("citationLegal"),
        "sourceExact": row.get("sourceExact"),
        "overclaimFlags": sorted(row.get("overclaimFlags", [])),
        "skippedReason": row.get("skippedReason"),
        "httpStatus": row.get("httpStatus"),
        "validationError": row.get("validationError"),
        "providerErrorCode": row.get("providerErrorCode"),
        "productionOutcome": row.get("productionOutcome"),
        "externalAttempted": row.get("externalAttempted"),
        "model": analysis.get("model", row.get("model")),
        "evidenceFingerprint": hashlib.sha256(
            json.dumps(row.get("contexts", []), sort_keys=True).encode()
        ).hexdigest(),
        "ratings": [
            {
                "requirement": item.get("requirement_id"),
                "level": (item.get("rating") or {}).get("level"),
                "citations": sorted(item.get("citation_ids", [])),
                "criteria": [
                    {
                        "criterion": c.get("criterion"),
                        "supported": c.get("supported"),
                        "citations": sorted(c.get("citation_ids", [])),
                    }
                    for c in ordered_records(
                        (item.get("rating") or {}).get("criteria", []), "criterion"
                    )
                ],
            }
            for item in items
        ],
    }


def wording(row):
    analysis = row.get("analysis") or {}
    return {
        "summary": analysis.get("summary"),
        "items": [
            {
                "requirement": item["requirement_id"],
                **{key: item.get(key) for key in ("explanation", "information_gap", "suggestion")},
                "ratingReason": (item.get("rating") or {}).get("reason"),
                "criteriaReasons": [
                    {"criterion": c["criterion"], "reason": c.get("reason")}
                    for c in ordered_records(
                        (item.get("rating") or {}).get("criteria", []), "criterion"
                    )
                ],
            }
            for item in ordered_records(analysis.get("items", []), "requirement_id")
        ],
    }


def case_records(run):
    if not isinstance(run, dict):
        raise ValueError("Evaluation run must be an object")
    return {row["id"]: row for row in ordered_records(run.get("results", []), "id")}


def compare(baseline, current):
    before, after = case_records(baseline), case_records(current)
    changes = []
    for case_id in sorted(before.keys() | after.keys()):
        old, new = before.get(case_id), after.get(case_id)
        if old is None or new is None:
            changes.append(
                {
                    "id": case_id,
                    "status": "added" if old is None else "not_run",
                    "humanSemanticReview": "pending",
                }
            )
            continue
        old_signals, new_signals = signals(old), signals(new)
        changed = [key for key in old_signals if old_signals[key] != new_signals[key]]
        old_output, new_output = bool(old.get("analysis")), bool(new.get("analysis"))
        model_comparison = (
            "both_outputs"
            if old_output and new_output
            else "baseline_only"
            if old_output
            else "current_only"
            if new_output
            else "neither_output"
        )
        changes.append(
            {
                "id": case_id,
                "status": "changed" if changed else "unchanged",
                "signalChanges": changed,
                "before": old_signals,
                "after": new_signals,
                "wordingChanged": wording(old) != wording(new),
                "modelComparison": model_comparison,
                "usageBefore": old.get("usage"),
                "usageAfter": new.get("usage"),
                "latencyBeforeMs": old.get("latencyMs"),
                "latencyAfterMs": new.get("latencyMs"),
                "humanSemanticReview": "pending",
            }
        )
    return changes


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--max-cases", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() == args.baseline.resolve():
        parser.error("Output must be new; frozen baselines are never overwritten")
    if args.live and (not args.allow_paid or args.current):
        parser.error("Live execution requires --allow-paid and no --current")
    if not args.live and not args.current:
        parser.error("Offline comparison requires --current")
    if not 1 <= args.max_cases <= 11:
        parser.error("max-cases must be 1..11")
    original = args.baseline.read_bytes()
    baseline = json.loads(original)
    baseline_rows = case_records(baseline)
    current_bytes = None
    if args.live:
        from app.agents.provider import EVIDENCE_PROMPT_VERSION
        from app.core.config import settings
        from evals.run_evidence_trust import evaluate_case

        cases = json.loads(Path(__file__).with_name("evidence-trust-cases.json").read_text("utf8"))
        ids = set(baseline_rows)
        known = {case["id"] for case in cases}
        if not ids or ids - known:
            parser.error("Live baseline must contain known fixed cases only")
        selected = [c for c in cases if c["id"] in ids][: args.max_cases]
        current = {
            "promptVersion": EVIDENCE_PROMPT_VERSION,
            "provider": settings.ai_provider,
            "configuredModel": settings.deepseek_model,
            "results": [],
        }
        for case in selected:
            current["results"].append(await evaluate_case(case, True))
    else:
        current_bytes = args.current.read_bytes()
        current = json.loads(current_bytes)
    record = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "live": args.live,
        "baselineFile": args.baseline.name,
        "baselineSha256": hashlib.sha256(original).hexdigest(),
        "baselinePromptVersion": baseline.get("promptVersion"),
        "currentPromptVersion": current.get("promptVersion"),
        "baselineProvider": baseline.get("provider"),
        "currentProvider": current.get("provider"),
        "baselineConfiguredModel": baseline.get("configuredModel"),
        "currentConfiguredModel": current.get("configuredModel"),
        "currentFile": args.current.name if args.current else None,
        "currentSha256": hashlib.sha256(current_bytes).hexdigest()
        if current_bytes is not None
        else None,
        "results": compare(baseline, current),
        "currentRun": current,
        "boundary": "Differences are clues; semantic correctness requires human review.",
    }
    if args.baseline.read_bytes() != original:
        raise RuntimeError("Frozen baseline changed during execution")
    if current_bytes is not None and args.current.read_bytes() != current_bytes:
        raise RuntimeError("Current evaluation changed during comparison")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as output:
        json.dump(record, output, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "live": args.live,
                "changedCases": sum(r["status"] == "changed" for r in record["results"]),
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
