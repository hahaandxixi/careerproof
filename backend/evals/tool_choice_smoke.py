"""Offline fixed tool-choice smoke for one Python requirement.

No model or database is used by default; the transport is synthetic. The guard
enforces the reviewed request shape before any physical POST.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

import httpx

from app.agents.evidence_workflow import build_evidence_contexts, run_evidence_workflow
from app.agents.provider import DeepSeekProvider
from app.core.config import settings
from app.tools.code_analyzer import CodeEvidence
from app.tools.matcher import MatchItemResult, MatchResult

MAX_REQUESTS = 4
MAX_INPUT = 30_000
MAX_OUTPUT = 4_000


class Guard:
    def __init__(self):
        self.attempts: list[dict] = []
        self.stopped = False
        self.stage = ""

    async def before_send(self, request):
        if self.stopped or len(self.attempts) >= MAX_REQUESTS:
            raise RuntimeError("tool smoke request allowance exhausted")
        if request.get("model") != "deepseek-flash":
            raise RuntimeError("unexpected model")
        if request.get("thinking") != {"type": "disabled"}:
            raise RuntimeError("thinking must be disabled")
        maximum = request.get("max_tokens")
        if type(maximum) is not int or not 1 <= maximum <= MAX_OUTPUT:
            raise RuntimeError("unexpected output bound")
        if self.stage.startswith("planning"):
            if not request.get("tools"):
                raise RuntimeError("planning must expose tools")
        elif request.get("tools"):
            raise RuntimeError("analysis must not expose tools")
        # Import locally so this eval is independent of the production estimator.
        from app.agents.input_budget import estimate_wire_input_bytes

        if estimate_wire_input_bytes(request) > MAX_INPUT:
            raise RuntimeError("input exceeds tool smoke bound")
        self.attempts.append({"stage": self.stage, "status": "send_intent"})
        return len(self.attempts) - 1

    async def after_response(self, attempt_id, payload, latency_ms):
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            self.stopped = True
            raise RuntimeError("missing usage")
        self.attempts[attempt_id].update(status="receipt_observed", usage=usage)

    async def on_failure(self, attempt_id, reason):
        self.stopped = True
        self.attempts[attempt_id].update(status="failed", reason=reason)


def load_python_case(report_path: Path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    item = next(row for row in report["items"] if row["skill"] == "Python")
    evidence = [
        CodeEvidence(
            skill=item["skill"], evidence_type=row.get("evidenceType") or "synthetic_code",
            file_path=row["filePath"], line_start=row["lineStart"], line_end=row["lineEnd"],
            snippet=row["snippet"], strength=row.get("strength") or "low",
            explanation=row.get("explanation") or "synthetic evidence",
            content_hash=row.get("contentHash") or "0" * 64,
            provenance=row.get("provenance"),
        )
        for row in item["evidenceList"]
    ]
    result = MatchResult(
        overall_score=None,
        items=[MatchItemResult(
            requirement_id=UUID(item["requirementId"]), requirement_title=item["requirementTitle"],
            skill=item["skill"], claimed=item["claimed"], claim_text=item["claimText"],
            evidence=evidence[0], evidence_list=evidence, verdict=item["verdict"],
            ai_confidence=None, rule_base_score=item["ruleBaseScore"], weight=item["weight"],
            final_score=item["finalScore"], explanation=item["explanation"],
            formula_version=item["formulaVersion"],
        )],
        gaps=[], claimed_only=[], summary="",
    )
    return result, item


def analysis_answer(item):
    cancel = "R1-E3"
    return {
        "summary": "工具补取后覆盖取消逻辑；运行结果仍未核验。",
        "items": [{
            "requirement_id": item["requirementId"],
            "explanation": "工具补取后看到取消函数；静态源码不等同于运行结果。",
            "citation_ids": [cancel],
            "information_gap": "运行结果、并发竞争与本人贡献未展示。",
            "suggestion": "补充运行记录和并发验证。",
            "confidence": 0.5,
            "rating": {
                "level": 2,
                "reason": "补取到取消实现，但未证明运行结果。",
                "criteria": [
                    {
                        "criterion": "relevance", "supported": True,
                        "citation_ids": [cancel], "reason": "取消函数直接相关。",
                    },
                    {
                        "criterion": "operation", "supported": True,
                        "citation_ids": [cancel], "reason": "存在取消状态变更。",
                    },
                    {
                        "criterion": "task", "supported": False,
                        "citation_ids": [], "reason": "运行与本人贡献未证实。",
                    },
                ],
            },
        }],
        "model": "deepseek-flash",
        "usage": {"input_tokens": 10, "output_tokens": 10, "cache_hit_tokens": 0, "latency_ms": 1},
    }


async def main(report_path: Path, output: Path) -> None:
    result, item = load_python_case(report_path)
    contexts = build_evidence_contexts(result, max_evidence=2)
    guard = Guard()

    def handler(request):
        body = json.loads(request.content)
        if body.get("tools"):
            return httpx.Response(200, json={
                "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{
                    "function": {
                        "name": "retrieve_more_evidence",
                        "arguments": json.dumps({
                            "requirement_id": item["requirementId"],
                            "query": "cancel 取消函数",
                        }),
                    }
                }]}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            })
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(analysis_answer(item), ensure_ascii=False),
            }}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        })

    provider = DeepSeekProvider(
        api_key="offline-not-a-real-key", base_url="https://api.deepseek.com",
        model="deepseek-flash", timeout_seconds=5, max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    settings.ai_external_enabled = True
    settings.ai_provider = "deepseek"
    settings.ai_context_evidence_limit = 2
    settings.ai_max_retrieval_calls = 2
    settings.ai_per_report_input_token_limit = MAX_INPUT
    settings.ai_per_report_output_token_limit = MAX_OUTPUT

    def factory(_provider, step):
        guard.stage = step
        return guard

    outcome = await run_evidence_workflow(
        result, provider_override=provider, external_allowed=True,
        durable_observer_factory=factory,
    )
    result_data = {
        "status": "pass" if outcome.analysis and not outcome.fallback_used else "fail",
        "toolCalls": list(outcome.tool_calls),
        "toolCompleted": any(row.get("status") == "completed" for row in outcome.tool_calls),
        "analysisCitations": sorted({
            cid
            for row in (outcome.analysis.items if outcome.analysis else [])
            for cid in row.citation_ids
        }),
        "requestCount": outcome.request_count,
        "attempts": guard.attempts,
        "fallback": outcome.fallback_used,
        "fallbackReason": outcome.fallback_reason,
        "contextEvidenceBefore": len(contexts[0].evidence),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result_data, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result_data["status"] == "pass" else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.report, args.output))
