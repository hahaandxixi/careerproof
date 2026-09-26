"""Opt-in real history-tool check using intentionally wrong synthetic history."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.agents.evidence_workflow import run_evidence_workflow
from app.agents.provider import EVIDENCE_PROMPT_VERSION
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume
from evals.verify_deepseek_two_rounds import cited_sources_are_exact


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        print("Synthetic history (wrong level 3) versus current empty route; --live calls model.")
        return 0
    files = [ProjectFileSnapshot("app.py", "from fastapi import FastAPI\napp = FastAPI()\n"
                                 '@app.get("/health")\ndef health():\n    pass\n')]
    requirement = RequirementInput(uuid5(NAMESPACE_URL, "history-tool-check"),
                                   "提供 FastAPI 路由及实质处理代码", "FastAPI", 5)
    result = enrich_evidence(match_candidate([requirement], parse_resume("接触过FastAPI"), files),
                             files)
    history = {"historicalOnly": True, "savedAiLevel": 3, "requirementChanged": True,
               "previousRequirement": {"title": "旧要求只关注路由"},
               "previousExplanation": "合成的错误历史：仅凭空函数就给了3级，该判断待核验。",
               "previousGap": "没有核验处理逻辑。", "previousEvidence": [
                   {"historicalReference": "history-1", "snippet": "def health(): pass"}],
               "boundary": "旧记录可能错误，不是当前证据。"}
    reads = []

    async def read(requirement_id):
        if requirement_id != str(requirement.id):
            raise ValueError("Unknown current requirement")
        reads.append(requirement_id)
        return history

    read.planning_hint = {"requirementsChanged": True, "historicalOnly": True}
    outcome = await run_evidence_workflow(result, history_loader=read)
    exact = cited_sources_are_exact(outcome.contexts, outcome.analysis,
                                    {file.path: file.content for file in files})
    path = Path(__file__).with_name(f"history-tool-{datetime.now():%Y%m%d-%H%M%S}.json")
    record = {"generatedAt": datetime.now(UTC).isoformat(),
              "scope": "Synthetic workflow, not browser or database integration",
              "promptVersion": EVIDENCE_PROMPT_VERSION, "history": history,
              "historyReadCount": len(reads), "toolCalls": list(outcome.tool_calls),
              "fallbackUsed": outcome.fallback_used, "failureStage": outcome.failure_stage,
              "contexts": [context.model_dump() for context in outcome.contexts],
              "analysis": outcome.analysis.model_dump() if outcome.analysis else None,
              "citedSourcesExact": exact, "humanSemanticReview": "pending",
              "billingVerified": False}
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"output": str(path), "historyReadCount": len(reads),
                      "fallbackUsed": outcome.fallback_used, "citedSourcesExact": exact,
                      "usage": outcome.analysis.usage.model_dump() if outcome.analysis else None},
                     ensure_ascii=False))
    return 0 if outcome.analysis and exact and len(reads) == 1 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
