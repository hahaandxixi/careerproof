"""Generate a source-linked synthetic report through the real evidence workflow."""

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.agents import evidence_workflow
from app.agents.provider import EVIDENCE_PROMPT_VERSION
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    markdown = args.output.with_suffix(".md")
    if args.output.exists() or markdown.exists():
        parser.error("Use new filenames; existing report history is preserved")
    demo = Path(__file__).resolve().parents[2] / "demo"
    files = [
        ProjectFileSnapshot(str(p.relative_to(demo / "evidence-api")), p.read_text("utf-8"))
        for p in sorted((demo / "evidence-api").rglob("*"))
        if p.is_file()
    ]
    skills = ["Python", "FastAPI", "PostgreSQL", "pytest", "Redis"]
    requirements = [
        RequirementInput(
            uuid5(NAMESPACE_URL, "demo-" + skill), f"提供{skill}开发实践材料", skill, 5
        )
        for skill in skills
    ]
    result = enrich_evidence(
        match_candidate(
            requirements, parse_resume((demo / "student-resume.txt").read_text("utf-8")), files
        ),
        files,
    )
    captured = {}
    original_factory = evidence_workflow.get_ai_provider

    def audited_provider():
        provider = original_factory()
        if provider.name != "mock":
            original_parser = provider._message_content

            def record(payload):
                captured["rawModelContent"] = (
                    payload.get("choices", [{}])[0].get("message", {}).get("content")
                )
                captured["rawUsage"] = payload.get("usage")
                return original_parser(payload)

            provider._message_content = record
        return provider

    evidence_workflow.get_ai_provider = audited_provider
    try:
        outcome = await evidence_workflow.run_evidence_workflow(result)
    finally:
        evidence_workflow.get_ai_provider = original_factory
    report = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "scope": "backend synthetic workflow; not browser or database acceptance",
        "promptVersion": EVIDENCE_PROMPT_VERSION,
        "ruleScore": result.overall_score,
        "ruleSummary": result.summary,
        "rules": [asdict(item) for item in result.items],
        "contexts": [context.model_dump() for context in outcome.contexts],
        "provider": outcome.provider,
        "model": outcome.model,
        "fallbackUsed": outcome.fallback_used,
        "fallbackReason": outcome.fallback_reason,
        "failureStage": outcome.failure_stage,
        "analysis": outcome.analysis.model_dump() if outcome.analysis else None,
        "attemptedUsage": outcome.attempted_usage.model_dump() if outcome.attempted_usage else None,
        "humanReview": "pending",
        "billingVerified": False,
        **captured,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), "utf-8")
    by_id = (
        {item.requirement_id: item for item in outcome.analysis.items} if outcome.analysis else {}
    )
    lines = [
        "# 合成材料证据报告",
        "",
        f"模型：{outcome.model}；规则材料支持度：{result.overall_score}",
        "",
        "本文件验证后端工作流，不代表浏览器或数据库验收。未执行上传代码，人工复核待完成。",
        "",
        outcome.analysis.summary if outcome.analysis else result.summary,
        "",
        f"降级：{outcome.fallback_used}；原因：{outcome.fallback_reason or '无'}",
        "",
    ]
    for context in outcome.contexts:
        lines += [f"## {context.skill}", ""]
        item = by_id.get(context.requirement_id)
        if item:
            lines += [
                item.explanation,
                "",
                f"缺口：{item.information_gap}",
                "",
                f"建议：{item.suggestion}",
                "",
                "引用：" + ", ".join(item.citation_ids),
                "",
            ]
        for evidence in context.evidence:
            source_path = demo / "evidence-api" / evidence.file_path
            source = source_path.as_posix()
            if source_path.drive:
                source = "/" + source
            lines += [
                f"### {evidence.citation_id}",
                "",
                f"[原文件 {evidence.file_path} 第 {evidence.line_start}–{evidence.line_end} 行]"
                f"(<{source}:{evidence.line_start}>)",
                "",
                evidence.context_note,
                "",
                "```text",
                evidence.snippet,
                "```",
                "",
            ]
    markdown.write_text("\n".join(lines), "utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "accepted": bool(outcome.analysis),
                "fallbackReason": outcome.fallback_reason,
                "requirements": len(by_id),
            }
        )
    )
    return 0 if outcome.analysis else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
