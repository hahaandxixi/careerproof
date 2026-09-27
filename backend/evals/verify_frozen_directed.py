"""Explicit paid opt-in for a synthetic, real DeepSeek directed-retrieval check.

No Docker, production database, user uploads, or real resumes are used.
Results stay local unless separately authorized for inclusion in Git.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.agents.evidence_workflow import build_evidence_contexts, run_evidence_workflow
from app.agents.provider import EVIDENCE_PROMPT_VERSION
from app.core.config import settings
from app.services.matching_materials import MatchMaterials, analyze_materials
from app.tools.matcher import RequirementInput
from evals.retrieval_context_cases import build_span_cases
from evals.verify_deepseek_two_rounds import cited_sources_are_exact


def synthetic_case():
    case = next(case for case in build_span_cases()["cases"] if case["id"] == "long_python")
    source = case["documents"][0]
    content = source["content"]
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with tempfile.TemporaryDirectory(prefix="careerproof-directed-") as directory:
        base = Path(directory)
        path = "synthetic-version/order.py"
        (base / path).parent.mkdir()
        (base / path).write_text(content, encoding="utf-8", newline="")
        materials = MatchMaterials(
            "合成学生接触过Python；贡献与运行记录待核验。",
            [
                {
                    "path": path,
                    "storageKey": path,
                    "hash": digest,
                    "size": len(content.encode("utf-8")),
                    "versionId": "synthetic-version",
                    "materialRole": "portfolio",
                    "sourceModality": "text",
                }
            ],
            [],
        )
        result = analyze_materials(
            [
                RequirementInput(
                    uuid5(NAMESPACE_URL, "frozen-directed-live-python-v1"),
                    "Python业务函数需核对输入校验、写入、异常清理与返回分支。",
                    "Python",
                    5,
                )
            ],
            materials,
            base,
            enable_semantic=False,
        )
    return result, {path: content}


def summarize_check(result, sources, outcome):
    initial = build_evidence_contexts(result, max_evidence=2)[0]
    covered = {
        (entry.file_path, line)
        for entry in initial.evidence
        for line in range(entry.line_start, entry.line_end + 1)
    }
    successful = [
        event
        for event in outcome.tool_calls
        if event.get("scope") == "current-frozen-materials"
        and event.get("resultCount") == 1
        and event.get("candidateCount", 0) > 0
    ]
    novel = [
        entry
        for context in outcome.contexts
        for entry in context.evidence
        if any(
            (entry.file_path, line) not in covered
            for line in range(entry.line_start, entry.line_end + 1)
        )
    ]
    cited = (
        {citation for item in outcome.analysis.items for citation in item.citation_ids}
        if outcome.analysis
        else set()
    )
    exact = cited_sources_are_exact(outcome.contexts, outcome.analysis, sources)
    all_exact = all(
        entry.file_path in sources
        and entry.snippet
        == "\n".join(sources[entry.file_path].splitlines()[entry.line_start - 1 : entry.line_end])
        for context in outcome.contexts
        for entry in context.evidence
    )
    return {
        "toolSelectedByRealModel": bool(successful),
        "novelSourceReturned": bool(novel),
        "novelSourceCited": any(entry.citation_id in cited for entry in novel),
        "rollbackVisibleAfterLookup": any("store.rollback()" in entry.snippet for entry in novel),
        "allContextsSourceExact": all_exact,
        "citedSourcesExact": exact,
        "contextBoundsPreserved": all(
            len(context.evidence) <= 3
            and all(
                entry.line_end - entry.line_start + 1 <= 40 and len(entry.snippet) <= 4000
                for entry in context.evidence
            )
            for context in outcome.contexts
        ),
        "ruleScoreUnchanged": (
            outcome.retrieval_result is not None
            and outcome.retrieval_result.overall_score == result.overall_score
        ),
        "initialRanges": [[entry.line_start, entry.line_end] for entry in initial.evidence],
        "novelRanges": [[entry.line_start, entry.line_end] for entry in novel],
    }


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.live and not args.allow_paid:
        parser.error("--live requires --allow-paid; no external request was made")
    result, sources = synthetic_case()
    if not args.live:
        print(
            json.dumps(
                {
                    "externalApiCalls": 0,
                    "live": False,
                    "initialRanges": [
                        [e.line_start, e.line_end]
                        for e in build_evidence_contexts(result)[0].evidence
                    ],
                }
            )
        )
        return 0
    if not args.output:
        parser.error("--output must name a new local record file")
    if settings.ai_provider != "deepseek" or not settings.ai_external_enabled:
        parser.error("DeepSeek must be the enabled provider")
    if not settings.deepseek_api_key or not settings.deepseek_api_key.get_secret_value().strip():
        parser.error("Local DeepSeek key is missing")
    # Reserve a fresh file before any paid work; never overwrite a frozen record.
    with args.output.open("x", encoding="utf-8") as output:
        started = datetime.now(UTC)
        progress = []

        async def record_progress(message):
            progress.append(message)

        outcome = await run_evidence_workflow(result, progress=record_progress)
        checks = summarize_check(result, sources, outcome)
        required = [key for key, value in checks.items() if isinstance(value, bool)]
        passed = (
            outcome.analysis is not None
            and not outcome.fallback_used
            and all(checks[key] for key in required)
        )
        usage = outcome.analysis.usage if outcome.analysis else outcome.attempted_usage
        data = {
            "startedAt": started.isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "scope": "Synthetic frozen material through real DeepSeek; no database/browser",
            "localRecordNotApprovedForGit": True,
            "syntheticLabelsIndependent": False,
            "provider": outcome.provider,
            "model": outcome.model,
            "promptVersion": EVIDENCE_PROMPT_VERSION,
            "sourceHashes": {
                path: hashlib.sha256(text.encode()).hexdigest() for path, text in sources.items()
            },
            "fallbackUsed": outcome.fallback_used,
            "fallbackReason": outcome.fallback_reason,
            "failureStage": outcome.failure_stage,
            "requestCount": outcome.request_count,
            "toolCalls": list(outcome.tool_calls),
            "checks": checks,
            "passed": passed,
            "progress": progress,
            "usage": usage.model_dump() if usage else None,
            "analysis": outcome.analysis.model_dump() if outcome.analysis else None,
            "contexts": [context.model_dump() for context in outcome.contexts],
            "humanSemanticReview": "pending",
            "billingVerified": False,
            "databasePersistenceVerified": False,
            "browserVerified": False,
        }
        json.dump(data, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "passed": passed,
                "checks": checks,
                "usage": data["usage"],
                "requestCount": outcome.request_count,
            },
            ensure_ascii=False,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
