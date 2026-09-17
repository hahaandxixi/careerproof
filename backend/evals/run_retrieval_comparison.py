"""Opt-in live comparison for no evidence, full evidence, and one tool call.

Only synthetic source code is sent. API keys and request headers are never persisted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.agents.contracts import overclaim_flags, validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts, execute_retrieval_tool
from app.agents.provider import EVIDENCE_PROMPT_VERSION, get_ai_provider
from app.core.config import settings
from app.tools.code_analyzer import CodeEvidence, ProjectFileSnapshot
from app.tools.matcher import RequirementInput, match_candidate


def synthetic_result():
    requirement = RequirementInput(
        uuid5(NAMESPACE_URL, "careerproof-retrieval-comparison"),
        "提供包含输入校验、服务调用和响应处理的 FastAPI 接口",
        "FastAPI",
        5,
    )
    result = match_candidate(
        [requirement],
        [],
        [
            ProjectFileSnapshot(
                "app/routes.py",
                "from fastapi import APIRouter\n"
                "router = APIRouter()\n"
                "@router.post('/items')\n"
                "def create_item(payload: dict):\n"
                "    if 'name' not in payload:\n"
                "        return {'error': 'name required'}\n"
                "    return {'item': save_item(payload['name'])}\n",
            )
        ],
    )
    evidence = [
        CodeEvidence(
            skill="FastAPI",
            evidence_type="fastapi_route",
            file_path="app/routes.py",
            line_start=3,
            line_end=7,
            snippet=(
                "@router.post('/items')\n"
                "def create_item(payload: dict):\n"
                "    if 'name' not in payload:\n"
                "        return {'error': 'name required'}\n"
                "    return {'item': save_item(payload['name'])}"
            ),
            strength="high",
            explanation="存在接口、输入分支和响应处理文本；未执行代码。",
            content_hash="1" * 64,
            context_complete=True,
            context_note="完整函数片段；运行结果和本人贡献仍需核验",
        ),
        CodeEvidence(
            skill="FastAPI",
            evidence_type="python_code",
            file_path="app/service.py",
            line_start=1,
            line_end=2,
            snippet="def save_item(name: str):\n    return {'name': name}",
            strength="medium",
            explanation="存在被路由调用的服务函数文本；持久化行为未展示。",
            content_hash="2" * 64,
            context_complete=False,
            context_note="局部函数片段；依赖和异常路径未展示",
        ),
        CodeEvidence(
            skill="FastAPI",
            evidence_type="pytest_test",
            file_path="tests/test_routes.py",
            line_start=4,
            line_end=7,
            snippet=(
                "def test_missing_name(client):\n"
                "    response = client.post('/items', json={})\n"
                "    assert response.json() == {'error': 'name required'}\n"
                "    assert response.status_code == 200"
            ),
            strength="high",
            explanation="存在测试函数和断言文本；不能据此断言测试已运行或通过。",
            content_hash="3" * 64,
            context_complete=True,
            context_note="完整测试函数；运行结果和本人贡献仍需核验",
        ),
    ]
    item = replace(
        result.items[0],
        evidence=evidence[0],
        evidence_list=evidence,
        verdict="supported",
        rule_base_score=0.65,
        final_score=65.0,
    )
    return replace(result, overall_score=65.0, items=[item])


def model_provider():
    settings.ai_external_enabled = True  # current process only; .env remains disabled
    settings.ai_provider = "zhipu"
    return get_ai_provider()


def metrics(contexts, analysis) -> dict:
    allowed = {c.requirement_id: {e.citation_id for e in c.evidence} for c in contexts}
    citation_legal = all(
        item.requirement_id in allowed
        and set(item.citation_ids).issubset(allowed[item.requirement_id])
        for item in analysis.items
    )
    text = " ".join(
        [analysis.summary]
        + [
            " ".join(filter(None, [item.explanation, item.information_gap, item.suggestion]))
            for item in analysis.items
        ]
    )
    levels = [item.rating.level for item in analysis.items if item.rating]
    supported = sum(
        criterion.supported
        for item in analysis.items
        if item.rating
        for criterion in item.rating.criteria
    )
    return {
        "citationLegal": citation_legal,
        "ratingCeilingRespected": all(
            item.rating is None
            or item.rating.level is None
            or item.rating.level <= context.rating_ceiling
            for item, context in zip(analysis.items, contexts, strict=True)
            if context.rating_ceiling is not None
        )
        and all(
            item.rating is None or item.rating.level is None
            for item, context in zip(analysis.items, contexts, strict=True)
            if context.rating_ceiling is None
        ),
        "ratingLevels": levels,
        "supportedCriteria": supported,
        "citationsUsed": sum(len(item.citation_ids) for item in analysis.items),
        "lexicalOverclaimFlags": overclaim_flags(text),
    }


def record_error(row: dict, exc: Exception) -> None:
    row["status"] = "error"
    row["errorType"] = type(exc).__name__
    row["error"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    if isinstance(exc, httpx.HTTPStatusError):
        row["httpStatus"] = exc.response.status_code
        with suppress(ValueError, AttributeError):
            row["providerErrorCode"] = exc.response.json().get("error", {}).get("code")


async def analyze_case(name: str, contexts) -> dict:
    row = {
        "case": name,
        "contexts": [context.model_dump() for context in contexts],
        "status": "pending",
        "manualSemanticReview": "pending",
    }
    provider = model_provider()
    started = perf_counter()
    try:
        analysis = await provider.analyze_evidence(contexts=contexts)
        validate_grounded_analysis(contexts, analysis)
        row.update(
            status="accepted",
            analysis=analysis.model_dump(),
            metrics=metrics(contexts, analysis),
        )
    except Exception as exc:
        record_error(row, exc)
    row["elapsedMs"] = round((perf_counter() - started) * 1000)
    return row


async def function_call_case(result) -> dict:
    contexts = build_evidence_contexts(result, max_evidence=2)
    row = {
        "case": "controlled_function_call",
        "initialContexts": [context.model_dump() for context in contexts],
        "status": "pending",
        "manualSemanticReview": "pending",
        "toolCall": None,
        "toolEvent": None,
    }
    provider = model_provider()
    started = perf_counter()
    try:
        call = await provider.plan_evidence_retrieval(contexts=contexts)
        if provider.planning_usage:
            row["planningUsage"] = provider.planning_usage.model_dump()
        if call:
            row["toolCall"] = call.model_dump()
            contexts, event = execute_retrieval_tool(result, contexts, call)
            row["toolEvent"] = event
        analysis = await provider.analyze_evidence(contexts=contexts)
        try:
            validate_grounded_analysis(contexts, analysis)
            row["repaired"] = False
        except ValueError as validation_error:
            row["rejectedAnalysis"] = analysis.model_dump()
            row["firstValidationError"] = str(validation_error)
            analysis = await provider.analyze_evidence(
                contexts=contexts,
                validation_feedback=str(validation_error),
                previous_analysis=analysis,
            )
            validate_grounded_analysis(contexts, analysis)
            row["repaired"] = True
        row.update(
            status="accepted",
            finalContexts=[context.model_dump() for context in contexts],
            analysis=analysis.model_dump(),
            metrics=metrics(contexts, analysis),
        )
    except Exception as exc:
        record_error(row, exc)
    row["elapsedMs"] = round((perf_counter() - started) * 1000)
    return row


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--interval", type=float, default=12)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--only",
        choices=("no_evidence", "three_retrieved_evidence", "controlled_function_call"),
        help="Run one case when retrying an incomplete provider call.",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("Explicit --live is required; the suite makes external model requests")
    if not 0 <= args.interval <= 120:
        parser.error("interval must be between 0 and 120 seconds")
    if settings.zhipu_api_key is None:
        parser.error("ZHIPU_API_KEY is missing")
    output = args.output or Path(
        f"evals/retrieval-comparison-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    if output.exists():
        raise SystemExit("Output already exists; use a new path to preserve history")
    result = synthetic_result()
    full_contexts = build_evidence_contexts(result, max_evidence=3)
    no_evidence_result = replace(
        result,
        overall_score=0.0,
        items=[
            replace(
                result.items[0],
                evidence=None,
                evidence_list=[],
                verdict="gap",
                rule_base_score=0.0,
                final_score=0.0,
            )
        ],
    )
    no_evidence_contexts = build_evidence_contexts(no_evidence_result)
    report = {
        "suite": "retrieval-comparison-v1",
        "generatedAt": datetime.now(UTC).isoformat(),
        "provider": "zhipu",
        "model": settings.zhipu_model,
        "promptVersion": EVIDENCE_PROMPT_VERSION,
        "syntheticDataOnly": True,
        "cases": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    runners = {
        "no_evidence": lambda: analyze_case("no_evidence", no_evidence_contexts),
        "three_retrieved_evidence": lambda: analyze_case("three_retrieved_evidence", full_contexts),
        "controlled_function_call": lambda: function_call_case(result),
    }
    selected = [args.only] if args.only else list(runners)
    for index, name in enumerate(selected):
        if index:
            await asyncio.sleep(args.interval)
        row = await runners[name]()
        report["cases"].append(row)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{row['case']}: {row['status']} ({row['elapsedMs']} ms)", flush=True)
    accepted = [row for row in report["cases"] if row["status"] == "accepted"]
    tool_case = next(
        (row for row in report["cases"] if row["case"] == "controlled_function_call"), None
    )
    report["summary"] = {
        "attempted": len(report["cases"]),
        "accepted": len(accepted),
        "citationLegalCount": sum(row["metrics"]["citationLegal"] for row in accepted),
        "overclaimFreeCount": sum(not row["metrics"]["lexicalOverclaimFlags"] for row in accepted),
        "toolRequested": bool(tool_case and tool_case.get("toolCall")),
        "toolReturnedEvidence": bool(
            tool_case and (tool_case.get("toolEvent") or {}).get("resultCount")
        ),
        "note": "结构校验不等于语义正确；结论支持度仍需人工复核。",
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    print(output, flush=True)
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
