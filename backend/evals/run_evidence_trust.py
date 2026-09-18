"""Source-to-model evaluation. Preserve all failures; never equate legal IDs with truth."""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.agents.contracts import overclaim_flags, validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.provider import EVIDENCE_PROMPT_VERSION, get_ai_provider
from app.core.config import settings
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume


async def evaluate_case(case: dict, live: bool) -> dict:
    files = [ProjectFileSnapshot(**file) for file in case["files"]]
    result = match_candidate(
        [RequirementInput(uuid5(NAMESPACE_URL, case["id"]), case["requirement"], case["skill"], 5)],
        parse_resume(case["resume"]),
        files,
    )
    result = enrich_evidence(result, files)
    contexts = build_evidence_contexts(result)
    row = {
        "id": case["id"],
        "rubric": case["rubric"],
        "ruleScore": result.overall_score,
        "ruleVerdict": result.items[0].verdict,
        "ruleSummary": result.summary,
        "contexts": [context.model_dump() for context in contexts],
        "sourceExact": all(
            e.snippet
            == "\n".join(
                next(f for f in files if f.path == e.file_path).content.splitlines()[
                    e.line_start - 1 : e.line_end
                ]
            )
            for context in contexts
            for e in context.evidence
        ),
        "accepted": None,
        "externalAttempted": False,
        "skippedReason": None,
        "rawModelContent": None,
        "validationError": None,
        "usage": None,
        "latencyMs": None,
        "citationLegal": None,
        "overclaimFlags": [],
        "humanReview": {
            "status": "pending",
            "conclusionSupported": None,
            "overclaimed": None,
            "reviewer": None,
            "note": None,
        },
    }
    if not live:
        return row
    if settings.ai_skip_when_no_evidence and not any(context.evidence for context in contexts):
        row["skippedReason"] = "no_evidence"
        row["productionOutcome"] = "rules_only"
        return row
    provider = get_ai_provider()
    if provider.name == "mock":
        raise ValueError("Live evaluation requires an enabled real provider")
    original = provider._message_content

    def record(payload):
        row["usage"] = payload.get("usage")
        row["rawModelContent"] = payload.get("choices", [{}])[0].get("message", {}).get("content")
        return original(payload)

    provider._message_content = record
    started = perf_counter()
    try:
        row["externalAttempted"] = True
        async with asyncio.timeout(settings.ai_workflow_timeout_seconds):
            analysis = await provider.analyze_evidence(contexts=contexts)
            row["analysis"] = analysis.model_dump()
            text = " ".join(
                [analysis.summary]
                + [
                    " ".join(
                        filter(None, [item.explanation, item.information_gap, item.suggestion])
                    )
                    for item in analysis.items
                ]
            )
            row["overclaimFlags"] = overclaim_flags(text)
            allowed = {c.requirement_id: {e.citation_id for e in c.evidence} for c in contexts}
            row["citationLegal"] = all(
                item.requirement_id in allowed
                and set(item.citation_ids) <= allowed[item.requirement_id]
                for item in analysis.items
            )
            validate_grounded_analysis(contexts, analysis)
            row["accepted"] = True
    except Exception as exc:
        row["accepted"] = False
        if isinstance(exc, httpx.HTTPStatusError):
            row["httpStatus"] = exc.response.status_code
            with suppress(ValueError, AttributeError):
                row["providerErrorCode"] = exc.response.json().get("error", {}).get("code")
        # Error class only for transport failures; never save request headers or credentials.
        row["validationError"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    row["latencyMs"] = round((perf_counter() - started) * 1000)
    return row


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--interval", type=float, default=30, help="Seconds between live cases")
    parser.add_argument(
        "--max-total-tokens",
        type=int,
        default=30_000,
        help="Stop before another case after provider-reported total usage reaches this value",
    )
    parser.add_argument("--only", action="append", help="Run only the named case; repeatable")
    parser.add_argument("--cases", type=Path, default=Path("evals/evidence-trust-cases.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.interval <= 300:
        parser.error("interval must be between 0 and 300 seconds")
    if not 1000 <= args.max_total_tokens <= 200_000:
        parser.error("max-total-tokens must be between 1000 and 200000")
    if args.output.exists():
        raise SystemExit("Output already exists: use a new run filename to preserve history")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.only:
        selected = set(args.only)
        known = {case["id"] for case in cases}
        unknown = selected - known
        if unknown:
            parser.error(f"unknown cases: {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["id"] in selected]
    rows = []
    report = {
        "suite": "evidence-trust-v2",
        "promptVersion": EVIDENCE_PROMPT_VERSION,
        "provider": settings.ai_provider if args.live else "rules",
        "intervalSeconds": args.interval if args.live else 0,
        "generatedAt": datetime.now(UTC).isoformat(),
        "live": args.live,
        "syntheticDataOnly": True,
        "maxTotalTokens": args.max_total_tokens if args.live else None,
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    reported_total_tokens = 0
    previous_external_attempted = False
    for case in cases:
        if args.live and reported_total_tokens >= args.max_total_tokens:
            budget_row = await evaluate_case(case, False)
            budget_row["skippedReason"] = "suite_token_limit"
            rows.append(budget_row)
            continue
        if args.live and previous_external_attempted:
            await asyncio.sleep(args.interval)
        rows.append(await evaluate_case(case, args.live))
        previous_external_attempted = bool(rows[-1].get("externalAttempted"))
        usage = rows[-1].get("usage") or {}
        reported_total_tokens += int(
            usage.get("total_tokens")
            or (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        )
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"{case['id']}: source={rows[-1]['sourceExact']}, accepted={rows[-1]['accepted']}",
            flush=True,
        )
    attempted = [r for r in rows if r["accepted"] is not None]
    measured = [r for r in attempted if r["citationLegal"] is not None]
    report["metrics"] = {
        "caseCount": len(rows),
        "attempted": len(attempted),
        "rulesOnlySkipped": sum(r.get("skippedReason") == "no_evidence" for r in rows),
        "suiteBudgetSkipped": sum(
            r.get("skippedReason") == "suite_token_limit" for r in rows
        ),
        "reportedTotalTokens": reported_total_tokens,
        "sourceExactRate": sum(r["sourceExact"] for r in rows) / len(rows),
        "acceptedRate": (
            sum(r["accepted"] for r in attempted) / len(attempted) if attempted else None
        ),
        "citationLegalityRate": sum(r["citationLegal"] for r in measured) / len(measured)
        if measured
        else None,
        "lexicalOverclaimRate": sum(bool(r["overclaimFlags"]) for r in measured) / len(measured)
        if measured
        else None,
        "conclusionSupportRate": None,
        "humanOverclaimRate": None,
        "humanReviewedCount": 0,
        "note": "Citation legality and lexical guards do not measure semantic correctness.",
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=True))
    return 0 if all(r["sourceExact"] for r in rows) and all(
        r["accepted"] for r in attempted
    ) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
