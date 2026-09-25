"""Reproduce a bounded, real-provider retrieval check on repository-owned synthetic code.

Run without --live to inspect candidate counts without spending model tokens.
With --live, write a new result file; never write credentials or request headers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.agents.evidence_workflow import run_evidence_workflow
from app.agents.provider import EVIDENCE_PROMPT_VERSION
from app.core.config import settings
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume


def synthetic_case():
    source_dir = Path(__file__).resolve().parents[2] / "demo" / "evidence-api"
    files = [
        ProjectFileSnapshot(path.relative_to(source_dir).as_posix(), path.read_text("utf-8"))
        for path in sorted(source_dir.rglob("*"))
        if path.is_file()
    ]
    requirements = [
        RequirementInput(
            uuid5(NAMESPACE_URL, f"two-round-{skill}"),
            title,
            skill,
            5,
        )
        for skill, title in (
            ("FastAPI", "提供 FastAPI 路由、处理和测试相关实践材料"),
            ("Python", "提供 Python 服务函数和数据处理实践材料"),
        )
    ]
    result = enrich_evidence(
        match_candidate(
            requirements,
            parse_resume("合成材料：接触过 FastAPI 与 Python，实际贡献和运行结果待核验。"),
            files,
        ),
        files,
    )
    return result, {file.path: file.content for file in files}


def cited_sources_are_exact(contexts, analysis, sources):
    if analysis is None:
        return False
    by_id = {context.requirement_id: context for context in contexts}
    for item in analysis.items:
        context = by_id.get(item.requirement_id)
        if context is None:
            return False
        by_citation = {evidence.citation_id: evidence for evidence in context.evidence}
        for citation_id in item.citation_ids:
            evidence = by_citation.get(citation_id)
            source = sources.get(evidence.file_path) if evidence else None
            if source is None:
                return False
            lines = source.splitlines()
            if "\n".join(lines[evidence.line_start - 1 : evidence.line_end]) != evidence.snippet:
                return False
    return True


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Call the configured real provider")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result, sources = synthetic_case()
    counts = {item.skill: len(item.evidence_list) for item in result.items}
    if not args.live:
        print(json.dumps({"candidateCounts": counts, "liveCall": False}, ensure_ascii=False))
        return 0
    if settings.ai_provider != "deepseek" or not settings.ai_external_enabled:
        parser.error("Real DeepSeek must be enabled in the local backend configuration")
    if any(count < 3 for count in counts.values()):
        parser.error("Both synthetic requirements need at least three source candidates")
    output = args.output or Path(__file__).with_name(
        f"deepseek-two-rounds-{datetime.now():%Y%m%d-%H%M%S}.json"
    )
    if output.exists():
        parser.error("Use a new output filename; prior evaluation records are immutable")
    progress: list[str] = []

    async def record(message: str) -> None:
        progress.append(message)

    outcome = await run_evidence_workflow(result, progress=record)
    source_exact = cited_sources_are_exact(outcome.contexts, outcome.analysis, sources)
    record_data = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "scope": (
            "Repository-owned synthetic code through backend workflow and real DeepSeek; "
            "no browser or database"
        ),
        "candidateCounts": counts,
        "provider": outcome.provider,
        "model": outcome.model,
        "promptVersion": EVIDENCE_PROMPT_VERSION,
        "fallbackUsed": outcome.fallback_used,
        "fallbackReason": outcome.fallback_reason,
        "failureStage": outcome.failure_stage,
        "requestCount": outcome.request_count,
        "progress": progress,
        "toolCalls": list(outcome.tool_calls),
        "contexts": [context.model_dump() for context in outcome.contexts],
        "usage": outcome.analysis.usage.model_dump() if outcome.analysis else None,
        "attemptedUsage": outcome.attempted_usage.model_dump()
        if outcome.attempted_usage
        else None,
        "citedSourcesExact": source_exact,
        "analysis": outcome.analysis.model_dump() if outcome.analysis else None,
        "humanSemanticReview": "pending",
        "billingVerified": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "fallbackUsed": outcome.fallback_used,
                "requestCount": outcome.request_count,
                "successfulRounds": [
                    event.get("round")
                    for event in outcome.tool_calls
                    if event.get("resultCount") == 1
                ],
                "citedSourcesExact": source_exact,
                "usage": record_data["usage"] or record_data["attemptedUsage"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if outcome.analysis and source_exact else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
