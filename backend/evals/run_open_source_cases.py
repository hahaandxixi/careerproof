"""Evaluate pinned public-source ZIPs and fictional resumes without running source code.

Run from the backend directory after demo/open-source/build_cases.py. The
default mode stays offline; --ai sends the bounded, source-checked contexts to
the configured provider and may incur a charge.
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

from app.agents import evidence_workflow
from app.agents.provider import EVIDENCE_PROMPT_VERSION, get_ai_provider
from app.core.config import settings
from app.services.matching_materials import MatchMaterials, analyze_materials
from app.tools.archive_scanner import ArchiveLimits
from app.tools.matcher import RequirementInput
from app.tools.material_processor import process_project

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "demo" / "open-source"
GENERATED = ROOT / "backend" / ".tmp" / "open-source-cases" / "generated"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _requirements(title: str) -> list[RequirementInput]:
    jobs = json.loads((ROOT / "demo" / "jobs.json").read_text(encoding="utf-8"))
    job = next((item for item in jobs if item["title"] == title), None)
    if job is None:
        raise ValueError(f"Unknown synthetic job: {title}")
    return [
        RequirementInput(
            uuid5(NAMESPACE_URL, f"open-source-case:{title}:{index}"),
            row["rawText"],
            row["skillName"],
            row["weight"],
        )
        for index, row in enumerate(job["requirements"], 1)
    ]


async def evaluate_case(case: dict, sources: dict[str, dict], *, ai: bool) -> dict:
    resume_path = FIXTURES / "resumes" / case["resume"]
    source = sources[case["project"]]
    archive = GENERATED / source["zip"]
    if _sha256(resume_path) != case["resumeSha256"] or _sha256(archive) != source["zipSha256"]:
        raise ValueError(f"Fixture changed since the manifest was generated: {case['id']}")
    with tempfile.TemporaryDirectory(prefix="careerproof-oss-case-") as temporary:
        storage = Path(temporary)
        records = process_project(
            archive,
            storage / "project",
            storage,
            archive.name,
            ArchiveLimits(
                settings.max_archive_bytes,
                settings.max_extracted_bytes,
                settings.max_file_bytes,
                settings.max_archive_files,
            ),
            settings.max_document_characters,
        )
        materials = MatchMaterials(
            resume_text=resume_path.read_text(encoding="utf-8"),
            files=[
                {
                    "path": row["relative_path"],
                    "storageKey": row["storage_key"],
                    "hash": row["content_hash"],
                    "size": row["size_bytes"],
                    "materialRole": "reference",
                }
                for row in records
            ],
            snapshots=[],
        )
        result = analyze_materials(_requirements(case["suggestedJob"]), materials, storage)
        output = {
            "caseId": case["id"],
            "job": case["suggestedJob"],
            "sourceRepo": source["repository"],
            "sourceCommit": source["commit"],
            "archiveSha256": source["zipSha256"],
            "resumeSha256": case["resumeSha256"],
            "indexedFiles": len(records),
            "expectedBoundary": case["expectedBoundary"],
            "ruleScore": result.overall_score,
            "ruleItems": [
                {
                    "skill": item.skill,
                    "verdict": item.verdict,
                    "claim": item.claimed,
                    "ruleScore": item.rule_base_score,
                    "evidence": [
                        {
                            "path": evidence.file_path,
                            "lines": [evidence.line_start, evidence.line_end],
                            "strength": evidence.strength,
                        }
                        for evidence in item.evidence_list[:3]
                    ],
                }
                for item in result.items
            ],
            "groundingError": result.grounding_error,
            "retrievalSteps": result.retrieval_steps,
        }
        if ai:
            validation_errors: list[str] = []
            original_validator = evidence_workflow.validate_grounded_analysis

            def record_validation(contexts, analysis):
                try:
                    return original_validator(contexts, analysis)
                except ValueError as exc:
                    # The checked-in validator emits fixed, bounded diagnostics.
                    validation_errors.append(str(exc)[:200])
                    raise

            evidence_workflow.validate_grounded_analysis = record_validation
            try:
                workflow = await evidence_workflow.run_evidence_workflow(result)
            finally:
                evidence_workflow.validate_grounded_analysis = original_validator
            output["ai"] = {
                "provider": workflow.provider,
                "model": workflow.model,
                "fallbackUsed": workflow.fallback_used,
                "fallbackReason": workflow.fallback_reason,
                "skippedReason": workflow.skipped_reason,
                "failureStage": workflow.failure_stage,
                "attemptedUsage": workflow.attempted_usage.model_dump()
                if workflow.attempted_usage
                else None,
                "analysis": workflow.analysis.model_dump() if workflow.analysis else None,
                "contexts": [context.model_dump() for context in workflow.contexts],
                "toolCalls": list(workflow.tool_calls),
                "validationErrors": validation_errors,
            }
        return output


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true", help="Call the configured real AI provider")
    parser.add_argument("--case", action="append", help="Limit to one or more case IDs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output filename; evaluation history is preserved")
    manifest = json.loads((GENERATED / "manifest.json").read_text(encoding="utf-8"))
    if args.ai and (not settings.ai_external_enabled or get_ai_provider().name == "mock"):
        parser.error("A real AI provider must be enabled in backend configuration")
    chosen = [
        case for case in manifest["cases"] if not args.case or case["id"] in args.case
    ]
    if not chosen or (args.case and set(args.case) != {case["id"] for case in chosen}):
        parser.error("Unknown or empty case selection")
    sources = {source["slug"]: source for source in manifest["sources"]}
    results = []
    for case in chosen:
        try:
            result = await evaluate_case(case, sources, ai=args.ai)
            results.append(result)
            print(
                json.dumps(
                    {
                        "caseId": case["id"],
                        "ruleScore": result["ruleScore"],
                        "aiFallback": result.get("ai", {}).get("fallbackUsed"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        except Exception as exc:
            results.append({"caseId": case["id"], "error": type(exc).__name__, "detail": str(exc)})
            print(f"{case['id']}: {type(exc).__name__}: {exc}", flush=True)
    report = {
        "suite": "open-source-synthetic-v1",
        "generatedAt": datetime.now(UTC).isoformat(),
        "scope": "backend upload parser, matching and optional AI workflow; not browser acceptance",
        "mode": "real-ai" if args.ai else "offline",
        "promptVersion": EVIDENCE_PROMPT_VERSION,
        "humanSemanticReview": "pending",
        "cases": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {args.output}")
    return 1 if any("error" in case for case in results) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
