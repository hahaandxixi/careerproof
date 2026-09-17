from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from app.agents.contracts import RequirementEvidenceContext, validate_grounded_analysis
from app.agents.provider import get_ai_provider


async def evaluate(cases: list[dict]) -> dict:
    contexts = [RequirementEvidenceContext.model_validate(case) for case in cases]
    provider = get_ai_provider()
    if provider.name == "mock":
        raise RuntimeError("Enable a real provider before running the AI baseline")
    analysis = await provider.analyze_evidence(contexts=contexts)
    validate_grounded_analysis(contexts, analysis)

    context_by_id = {context.requirement_id: context for context in contexts}
    total_citations = 0
    valid_citations = 0
    grounded_expected = 0
    grounded_returned = 0
    gap_expected = 0
    gap_complete = 0
    boundary_compliant = 0
    results = []
    for item in analysis.items:
        context = context_by_id[item.requirement_id]
        allowed = {evidence.citation_id for evidence in context.evidence}
        citations_valid = all(citation in allowed for citation in item.citation_ids)
        total_citations += len(item.citation_ids)
        valid_citations += sum(citation in allowed for citation in item.citation_ids)
        expects_grounding = bool(context.evidence) and context.verdict in {"supported", "partial"}
        if expects_grounding:
            grounded_expected += 1
            grounded_returned += bool(item.citation_ids)
        expects_gap = context.verdict in {"partial", "claimed_only", "gap", "unsupported"}
        if expects_gap:
            gap_expected += 1
            gap_complete += bool(item.information_gap and item.suggestion)
        combined = " ".join(
            value for value in (item.explanation, item.information_gap, item.suggestion) if value
        )
        forbidden = ("不具备该能力", "没有该能力", "能力不足")
        boundary_ok = not any(phrase in combined for phrase in forbidden)
        if context.verdict == "unsupported":
            boundary_ok = boundary_ok and any(
                marker in combined
                for marker in ("规则", "暂不支持", "无法评估", "不能判断", "无法判断")
            )
            boundary_ok = boundary_ok and not any(
                phrase in combined for phrase in ("无关", "移除", "删除")
            )
        boundary_compliant += boundary_ok
        results.append(
            {
                "id": item.requirement_id,
                "verdict": context.verdict,
                "citationIds": item.citation_ids,
                "citationsValid": citations_valid,
                "boundaryCompliant": boundary_ok,
                "explanation": item.explanation,
                "informationGap": item.information_gap,
                "suggestion": item.suggestion,
            }
        )

    case_count = len(contexts)
    return {
        "suite": "ai-evidence-v1",
        "generatedAt": datetime.now(UTC).isoformat(),
        "provider": provider.name,
        "model": analysis.model,
        "caseCount": case_count,
        "requirementCoverage": round(len(analysis.items) / case_count, 4),
        "citationPrecision": round(valid_citations / total_citations, 4)
        if total_citations
        else 1,
        "groundedItemRate": round(grounded_returned / grounded_expected, 4)
        if grounded_expected
        else 1,
        "gapCompleteness": round(gap_complete / gap_expected, 4) if gap_expected else 1,
        "boundaryCompliance": round(boundary_compliant / case_count, 4),
        "ungroundedCitationCount": total_citations - valid_citations,
        "inputTokens": analysis.usage.input_tokens,
        "outputTokens": analysis.usage.output_tokens,
        "latencyMs": analysis.usage.latency_ms,
        "summary": analysis.summary,
        "results": results,
    }


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Run the grounded AI evidence baseline")
    parser.add_argument("--cases", type=Path, default=Path("evals/ai-evidence-cases.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = await evaluate(json.loads(args.cases.read_text(encoding="utf-8")))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    metrics = (
        report["requirementCoverage"],
        report["citationPrecision"],
        report["groundedItemRate"],
        report["gapCompleteness"],
        report["boundaryCompliance"],
    )
    return 0 if metrics == (1, 1, 1, 1, 1) else 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
