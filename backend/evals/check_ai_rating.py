"""One opt-in synthetic model request. Never reads uploaded candidate materials."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import evidence_workflow  # noqa: E402
from app.agents.evidence_workflow import run_evidence_workflow  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.tools.code_analyzer import ProjectFileSnapshot  # noqa: E402
from app.tools.evidence_context import enrich_evidence  # noqa: E402
from app.tools.matcher import RequirementInput, match_candidate  # noqa: E402
from app.tools.resume_parser import parse_resume  # noqa: E402


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("Explicit --live required for one external synthetic request")
    settings.ai_external_enabled = True  # This process only; .env is unchanged.
    settings.ai_provider = "zhipu"
    files = [
        ProjectFileSnapshot(
            "synthetic.py",
            "from fastapi import FastAPI\n"
            'app = FastAPI()\n@app.get("/items")\ndef items():\n    pass\n',
        )
    ]
    result = match_candidate(
        [RequirementInput(uuid4(), "提供处理数据并返回结果的 FastAPI 接口", "FastAPI", 5)],
        parse_resume("熟悉 FastAPI，声明仅为测试文本"),
        files,
    )
    result = enrich_evidence(result, files)
    captured = {}
    validate = evidence_workflow.validate_grounded_analysis

    def capture_validation(contexts, analysis):
        captured["raw_analysis"] = analysis.model_dump()
        try:
            validate(contexts, analysis)
        except ValueError as exc:
            captured["validation_error"] = str(exc)
            raise

    evidence_workflow.validate_grounded_analysis = capture_validation
    start = perf_counter()
    outcome = await run_evidence_workflow(result)
    analysis = outcome.analysis
    rating = analysis.items[0].rating if analysis else None
    report = dict(
        case="synthetic-empty-function",
        elapsed_seconds=round(perf_counter() - start, 3),
        fallback=outcome.fallback_used,
        reason=outcome.fallback_reason,
        analysis=analysis.model_dump() if analysis else None,
        attempted_usage=outcome.attempted_usage.model_dump() if outcome.attempted_usage else None,
        expected="相关线索最多1级；不能把pass认定为实质操作或完整任务",
        passed=rating is not None and rating.level in (None, 1),
        context=[c.model_dump() for c in outcome.contexts],
        diagnostics=captured,
    )
    path = Path(__file__).with_name("ai-rating-smoke-20260917.json")
    index = 2
    while path.exists():
        path = Path(__file__).with_name(f"ai-rating-smoke-20260917-run{index}.json")
        index += 1
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: report[k] for k in ("case", "elapsed_seconds", "fallback", "reason", "passed")}
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
