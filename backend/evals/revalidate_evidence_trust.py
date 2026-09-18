"""Revalidate saved synthetic model responses without making network requests."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.agents.contracts import (
    EvidenceAnalysis,
    RequirementEvidenceContext,
    overclaim_flags,
    validate_grounded_analysis,
)
from app.agents.provider import parse_provider_json_object


def revalidate(row: dict, model: str) -> dict:
    result = {
        "status": "not_applicable",
        "jsonRepairUsed": False,
        "citationLegal": None,
        "lexicalOverclaimFlags": [],
        "validationError": None,
    }
    raw = row.get("rawModelContent")
    if not raw:
        result["status"] = "skipped" if row.get("skippedReason") else "no_output"
        return result
    try:
        parsed, repaired = parse_provider_json_object(raw)
        result["jsonRepairUsed"] = repaired
        usage = row.get("usage") or {}
        parsed.update(
            {
                "model": model,
                "usage": {
                    "input_tokens": int(usage.get("prompt_tokens") or 0),
                    "output_tokens": int(usage.get("completion_tokens") or 0),
                    "cache_hit_tokens": int(
                        (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
                    ),
                    "latency_ms": int(row.get("latencyMs") or 0),
                },
            }
        )
        analysis = EvidenceAnalysis.model_validate(parsed)
        contexts = [RequirementEvidenceContext.model_validate(item) for item in row["contexts"]]
        allowed = {
            context.requirement_id: {evidence.citation_id for evidence in context.evidence}
            for context in contexts
        }
        result["citationLegal"] = all(
            item.requirement_id in allowed
            and set(item.citation_ids).issubset(allowed[item.requirement_id])
            for item in analysis.items
        )
        text = " ".join(
            [analysis.summary]
            + [
                " ".join(
                    value
                    for value in (item.explanation, item.information_gap, item.suggestion)
                    if value
                )
                for item in analysis.items
            ]
        )
        result["lexicalOverclaimFlags"] = overclaim_flags(text)
        validate_grounded_analysis(contexts, analysis)
        result.update(
            {
                "status": "accepted",
                "analysis": analysis.model_dump(),
            }
        )
    except Exception as exc:
        result["status"] = "rejected"
        result["validationError"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output already exists: preserve prior evaluation files")
    source = json.loads(args.input.read_text(encoding="utf-8"))
    model = "deepseek-flash"
    results = [
        {"id": row["id"], **revalidate(row, model)} for row in source.get("results", [])
    ]
    attempted = [row for row in results if row["status"] in {"accepted", "rejected"}]
    accepted = [row for row in attempted if row["status"] == "accepted"]
    report = {
        "suite": "evidence-trust-offline-revalidation-v1",
        "generatedAt": datetime.now(UTC).isoformat(),
        "sourceFile": args.input.name,
        "provider": source.get("provider"),
        "model": model,
        "networkRequests": 0,
        "results": results,
        "metrics": {
            "caseCount": len(results),
            "attemptedResponses": len(attempted),
            "acceptedResponses": len(accepted),
            "acceptedRate": len(accepted) / len(attempted) if attempted else None,
            "jsonRepairCount": sum(row["jsonRepairUsed"] for row in results),
            "citationLegalityRate": (
                sum(bool(row["citationLegal"]) for row in accepted) / len(accepted)
                if accepted
                else None
            ),
            "lexicalOverclaimRate": (
                sum(bool(row["lexicalOverclaimFlags"]) for row in accepted) / len(accepted)
                if accepted
                else None
            ),
            "conclusionSupportRate": None,
            "humanOverclaimRate": None,
            "note": "Structural acceptance and lexical guards are not independent semantic review.",
        },
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False))
    return 0 if len(accepted) == len(attempted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
