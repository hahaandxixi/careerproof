"""Opt-in synthetic evidence smoke; fixed single-call packet and bounded Agent batch."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from app.agents.contracts import validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts, run_evidence_workflow
from app.agents.provider import (
    DeepSeekProvider,
    conservative_input_token_estimate,
    get_ai_provider,
)
from app.core.config import settings
from app.tools.code_analyzer import CodeEvidence, ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import MatchItemResult, MatchResult, RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume

ROOT = Path(__file__).resolve().parents[2]
CASE_IDS = ("route-body", "empty-route", "contradictory-return")
BATCH_ID = "current-smoke-20261018-three-cases"
AGENT_CASE_IDS = ("AG-01", "AG-02", "AG-03")
AGENT_BATCH_ID = "agent-live-20261020-three-cases"
AGENT_MAX_PER_CASE = 4
AGENT_MAX_BATCH = 12
AGENT_INPUT_LIMIT = 20_000
AGENT_OUTPUT_LIMIT = 1_200
AGENT_CEILING_YUAN = Decimal("2")
STATE_ROOT = ROOT / "backend/.tmp/ai-smoke"


class SmokeStopped(ValueError):
    pass


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class RequestGuard:
    """Admission happens before every physical POST, including provider retries."""

    def __init__(self, input_price: Decimal, output_price: Decimal, checkpoint=lambda: None):
        if any(not price.is_finite() or price <= 0 for price in (input_price, output_price)):
            raise SmokeStopped("Invalid prices")
        self.input_price, self.output_price = input_price, output_price
        self.reserved = Decimal(0)
        self.attempts: list[dict] = []
        self.stopped = False
        self.expected_hash = ""
        self.case_id = ""
        self.checkpoint = checkpoint

    async def before_send(self, request: dict) -> int:
        if self.stopped or len(self.attempts) >= 3:
            raise SmokeStopped("Physical-request allowance exhausted or batch stopped")
        if payload_hash(request) != self.expected_hash:
            raise SmokeStopped("Request differs from the reviewed packet")
        bound = conservative_input_token_estimate(request["messages"])
        if (
            request.get("model") != "deepseek-flash"
            or request.get("thinking") != {"type": "disabled"}
            or bound > 20_000
            or type(request.get("max_tokens")) is not int
            or not 1 <= request["max_tokens"] <= 1_200
        ):
            raise SmokeStopped("Request exceeds the fixed smoke contract")
        # Reserve worst permitted input/output, never release on failed/unknown usage.
        reserve = (20_000 * self.input_price + 1_200 * self.output_price) / 1_000_000
        if self.reserved + reserve > Decimal("1"):
            raise SmokeStopped("One-yuan reservation ceiling exceeded before POST")
        self.reserved += reserve
        self.attempts.append({"case": self.case_id, "status": "send_intent", "response": None})
        self.checkpoint()  # If recording fails, provider never reaches HTTP.
        return len(self.attempts) - 1

    async def after_response(self, attempt_id: int, payload: dict, latency_ms: int):
        row = self.attempts[attempt_id]
        row.update(response=payload, latencyMs=latency_ms, status="response_observed")
        usage = payload.get("usage")
        counts = (
            [usage.get(key) for key in ("prompt_tokens", "completion_tokens")]
            if isinstance(usage, dict)
            else []
        )
        if (
            len(counts) != 2
            or any(type(value) is not int or value < 0 for value in counts)
            or counts[0] > 20_000
            or counts[1] > 1_200
        ):
            self.stopped = True
            row["status"] = "usage_untrusted"
            self.checkpoint()
            raise SmokeStopped("Usage missing, invalid or above reservation; no further sends")
        row["status"] = "receipt_observed"
        self.checkpoint()

    async def on_failure(self, attempt_id: int, reason: str):
        self.stopped = True
        self.attempts[attempt_id].update(status="failed", reason=reason)
        self.checkpoint()


class AgentRequestGuard(RequestGuard):
    """Batch guard for the two-round Agent workflow.

    Unlike the fixed single-request smoke, requests legitimately differ after a
    tool result. The guard therefore validates model/tool contracts and source
    membership, and records each actual request hash instead of requiring one
    precomputed packet hash.
    """

    def __init__(self, input_price: Decimal, output_price: Decimal, checkpoint=lambda: None):
        super().__init__(input_price, output_price, checkpoint)
        self.case_counts: dict[str, int] = {}
        self.stage = ""
        self.allowed_requirement = ""
        self.allowed_paths: set[str] = set()
        self.allowed_evidence: dict[str, tuple[str, int, int, str]] = {}
        self.history_allowed = False
        self.history_hash = ""
        self.hard_stop_reason = ""

    def begin_case(self, case: dict) -> None:
        self.case_id = str(case["id"])
        self.stage = ""
        self.allowed_requirement = str(case["requirementId"])
        self.allowed_paths = {str(path) for path in case["allowedPaths"]}
        self.allowed_evidence = {
            f"R1-E{index}": (
                str(item["filePath"]),
                int(item["lineStart"]),
                int(item["lineEnd"]),
                str(item["snippet"]),
            )
            for index, item in enumerate(case["evidence"], 1)
        }
        history = case.get("history")
        self.history_allowed = history is not None
        self.history_hash = payload_hash(history) if history is not None else ""

    def validate_contexts(self, contexts) -> None:
        if len(contexts) != 1 or str(contexts[0].requirement_id) != self.allowed_requirement:
            raise SmokeStopped("Agent context requirement is outside the fixed case")
        context = contexts[0]
        if len(context.evidence) > 3:
            raise SmokeStopped("Agent context exceeds three citations")
        for evidence in context.evidence:
            allowed = self.allowed_evidence.get(evidence.citation_id)
            if allowed is None:
                raise SmokeStopped("Agent context contains an unauthorized citation identity")
            expected = (
                evidence.file_path,
                evidence.line_start,
                evidence.line_end,
                evidence.snippet,
            )
            if expected != allowed:
                raise SmokeStopped("Agent context citation/path/line/snippet does not match packet")

    def validate_history(self, history: dict | None) -> None:
        if history is None:
            return
        if not self.history_allowed:
            raise SmokeStopped("History context is not allowed for this case")
        if history.get("previousReportId") is None:
            raise SmokeStopped("History context is missing its frozen report identity")
        if payload_hash(history) != self.history_hash:
            raise SmokeStopped("History context identity/content changed")

    async def after_response(self, attempt_id: int, payload: dict, latency_ms: int):
        try:
            await super().after_response(attempt_id, payload, latency_ms)
        except SmokeStopped as exc:
            self.stopped = True
            self.hard_stop_reason = str(exc)
            raise
        except Exception as exc:
            # A trusted usage payload is not a durable receipt. The workflow may
            # catch the provider's persistence error and fall back, so latch the
            # batch stop here before that exception leaves the observer.
            self.stopped = True
            self.hard_stop_reason = "receipt_checkpoint_failed"
            self.attempts[attempt_id]["status"] = "receipt_persistence_failed"
            raise SmokeStopped("Agent receipt checkpoint failed") from exc

    async def on_failure(self, attempt_id: int, reason: str):
        self.hard_stop_reason = reason
        await super().on_failure(attempt_id, reason)

    async def before_send(self, request: dict) -> int:
        if self.stopped:
            raise SmokeStopped("Agent batch already stopped")
        if self.case_id not in AGENT_CASE_IDS:
            raise SmokeStopped("Unknown Agent case")
        if self.stage not in {"planning_1", "planning_2", "analysis", "repair"}:
            raise SmokeStopped("Unknown Agent workflow stage")
        case_count = self.case_counts.get(self.case_id, 0)
        if case_count >= AGENT_MAX_PER_CASE or len(self.attempts) >= AGENT_MAX_BATCH:
            raise SmokeStopped("Per-case or batch physical-request allowance exhausted")
        if (
            request.get("model") != "deepseek-flash"
            or request.get("thinking") != {"type": "disabled"}
            or type(request.get("max_tokens")) is not int
            or not 1 <= request["max_tokens"] <= AGENT_OUTPUT_LIMIT
            or conservative_input_token_estimate(request["messages"]) > AGENT_INPUT_LIMIT
        ):
            raise SmokeStopped("Agent request exceeds the fixed model/input contract")
        tools = request.get("tools")
        if self.stage.startswith("planning"):
            if not isinstance(tools, list) or request.get("tool_choice") != "auto":
                raise SmokeStopped("Planning request must expose the fixed tools with auto choice")
            names = [
                item.get("function", {}).get("name")
                for item in tools
                if isinstance(item, dict)
            ]
            if any(
                name not in {"retrieve_more_evidence", "get_previous_report_context"}
                for name in names
            ):
                raise SmokeStopped("Planning request exposed an unauthorized tool")
        elif tools:
            raise SmokeStopped("Analysis/repair request must not expose tools")
        reserve = (
            AGENT_INPUT_LIMIT * self.input_price + AGENT_OUTPUT_LIMIT * self.output_price
        ) / 1_000_000
        if self.reserved + reserve > AGENT_CEILING_YUAN:
            raise SmokeStopped("Agent batch reservation ceiling exceeded before POST")
        self.reserved += reserve
        self.case_counts[self.case_id] = case_count + 1
        self.attempts.append({
            "case": self.case_id,
            "stage": self.stage,
            "status": "send_intent",
            "requestSha256": payload_hash(request),
            "response": None,
        })
        try:
            self.checkpoint()
        except Exception as exc:
            # Admission was recorded, but the durable write failed. Treat it as
            # a hard stop: the provider must not reach HTTP.
            self.stopped = True
            self.hard_stop_reason = "checkpoint_failed"
            raise SmokeStopped("Agent send-intent checkpoint failed") from exc
        return len(self.attempts) - 1


def check_agent_packet(packet: dict) -> None:
    if tuple(row["id"] for row in packet["cases"]) != AGENT_CASE_IDS:
        raise SmokeStopped("Only AG-01/AG-02/AG-03 are permitted")
    if packet.get("batchId") != AGENT_BATCH_ID:
        raise SmokeStopped("Agent packet batch id mismatch")
    if packet.get("limits") != {
        "perCasePhysicalRequests": AGENT_MAX_PER_CASE,
        "batchPhysicalRequests": AGENT_MAX_BATCH,
        "inputUpperBoundPerRequest": AGENT_INPUT_LIMIT,
        "outputLimitPerRequest": AGENT_OUTPUT_LIMIT,
        "ceilingYuan": str(AGENT_CEILING_YUAN),
    }:
        raise SmokeStopped("Agent packet limits do not match the reviewed contract")
    for relative, expected in packet["sourceHashes"].items():
        path = (ROOT / relative).resolve()
        if (
            not path.is_relative_to(ROOT)
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise SmokeStopped("Agent reviewed source changed")
    for row in packet["cases"]:
        if not row.get("requirementId") or not row.get("evidence"):
            raise SmokeStopped("Agent case is missing fixed requirement/evidence")
        if any(item.get("filePath") not in row["allowedPaths"] for item in row["evidence"]):
            raise SmokeStopped("Agent evidence path is outside the fixed case")


def _agent_result(row: dict) -> MatchResult:
    evidence = [
        CodeEvidence(
            skill=row["skill"],
            evidence_type=str(item.get("evidenceType") or "synthetic_code"),
            file_path=item["filePath"],
            line_start=item["lineStart"],
            line_end=item["lineEnd"],
            snippet=item["snippet"],
            strength=item.get("strength") or "low",
            explanation=item.get("explanation") or "合成固定证据。",
            content_hash=hashlib.sha256(item["snippet"].encode("utf-8")).hexdigest(),
            context_complete=bool(item.get("contextComplete")),
            context_note=item.get("contextNote") or "合成固定上下文",
        )
        for item in row["evidence"]
    ]
    requirement_id = UUID(row["requirementId"])
    item = MatchItemResult(
        requirement_id=requirement_id,
        requirement_title=row["requirement"],
        skill=row["skill"],
        claimed=True,
        claim_text=row["resume"],
        evidence=evidence[0] if evidence else None,
        evidence_list=evidence,
        verdict="partial",
        ai_confidence=None,
        rule_base_score=0.4,
        weight=5,
        final_score=40,
        explanation="合成规则证据，仅用于 Agent 工具链观察。",
        formula_version="synthetic-agent-v1",
    )
    return MatchResult(
        overall_score=40,
        items=[item],
        gaps=["运行结果与本人贡献仍需核验。"],
        claimed_only=[],
        summary="合成 Agent 验证材料；不构成真实能力结论。",
    )


def _agent_analysis(row: dict, citation: str) -> dict:
    return {
        "summary": "合成材料只展示代码线索，不能证明运行或录用。",
        "items": [{
            "requirement_id": row["requirementId"],
            "explanation": "所选引用只支持存在相关实现线索，运行与贡献仍待核验。",
            "citation_ids": [citation],
            "information_gap": "运行结果、测试执行与本人贡献未证明。",
            "suggestion": "补充可定位的运行记录并说明本人负责部分。",
            "confidence": 0.5,
            "rating": {
                "level": 1,
                "reason": "仅有相关实现线索。",
                "criteria": [
                    {
                        "criterion": "relevance",
                        "supported": True,
                        "citation_ids": [citation],
                        "reason": "引用与要求相关。",
                    },
                    {
                        "criterion": "operation",
                        "supported": False,
                        "citation_ids": [],
                        "reason": "未展示运行。",
                    },
                    {
                        "criterion": "task",
                        "supported": False,
                        "citation_ids": [],
                        "reason": "未展示完整任务。",
                    },
                ],
            },
        }],
    }


async def execute_agent(packet: dict, output: Path, prices: tuple[Decimal, Decimal]) -> dict:
    check_agent_packet(packet)
    report = {
        "batch": AGENT_BATCH_ID,
        "status": "started",
        "results": [],
        "humanReview": None,
        "attempts": [],
        "reservedYuan": "0",
        "syntheticOnly": True,
        "externalRequests": 0,
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream)
    guard = AgentRequestGuard(*prices)
    batch_path = None

    def save():
        report.update(
            attempts=guard.attempts,
            reservedYuan=str(guard.reserved),
            externalRequests=len(guard.attempts),
        )
        content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if batch_path is not None:
            batch_path.write_text(content, encoding="utf-8")
        output.write_text(content, encoding="utf-8")

    guard.checkpoint = save

    def observer(_provider, step):
        guard.stage = step
        return guard

    old_input_limit = settings.ai_per_report_input_token_limit
    old_output_limit = settings.ai_per_report_output_token_limit
    settings.ai_per_report_input_token_limit = min(old_input_limit, AGENT_INPUT_LIMIT)
    settings.ai_per_report_output_token_limit = min(old_output_limit, AGENT_OUTPUT_LIMIT)
    try:
        batch_path = claim_batch(STATE_ROOT, AGENT_BATCH_ID)
        save()
        provider = get_ai_provider()
        if not isinstance(provider, DeepSeekProvider):
            raise SmokeStopped("Current enabled provider must be official DeepSeek Flash")
        provider._max_attempts = 1
        provider._timeout = 30
        original_plan = provider.plan_evidence_retrieval
        original_analyze = provider.analyze_evidence

        def stop_http(error):
            # Non-retryable HTTP errors do not invoke the production observer's
            # on_failure hook. Stop this eval batch without changing that policy.
            guard.stopped = True
            guard.hard_stop_reason = f"provider_http_{error.response.status_code}"
            if guard.attempts:
                guard.attempts[-1]["httpStatus"] = error.response.status_code

        async def guarded_plan(**kwargs):
            try:
                guard.validate_contexts(kwargs["contexts"])
                return await original_plan(**kwargs)
            except SmokeStopped as exc:
                guard.stopped = True
                guard.hard_stop_reason = str(exc)
                raise
            except httpx.HTTPStatusError as exc:
                stop_http(exc)
                raise

        async def guarded_analyze(**kwargs):
            try:
                guard.validate_contexts(kwargs["contexts"])
                guard.validate_history(getattr(provider, "history_context", None))
                return await original_analyze(**kwargs)
            except SmokeStopped as exc:
                guard.stopped = True
                guard.hard_stop_reason = str(exc)
                raise
            except httpx.HTTPStatusError as exc:
                stop_http(exc)
                raise

        provider.plan_evidence_retrieval = guarded_plan
        provider.analyze_evidence = guarded_analyze
        hard_stopped = False
        had_fallback = False
        for row in packet["cases"]:
            guard.begin_case(row)
            provider.history_context = None
            requests_before = len(guard.attempts)
            history = None
            if row.get("history") is not None:
                async def load(_requirement_id, fixed_history=row["history"]):
                    guard.validate_history(fixed_history)
                    return fixed_history
                history = load
            current = {"id": row["id"], "humanReview": None, "accepted": None}
            report["results"].append(current)
            outcome = await run_evidence_workflow(
                _agent_result(row),
                history_loader=history,
                durable_observer_factory=observer,
                provider_override=provider,
            )
            current.update({
                "fallbackUsed": outcome.fallback_used,
                "fallbackReason": outcome.fallback_reason,
                "failureStage": outcome.failure_stage,
                "toolCalls": list(outcome.tool_calls),
                "requestCount": len(guard.attempts) - requests_before,
                "analysis": outcome.analysis.model_dump() if outcome.analysis else None,
                "accepted": bool(outcome.analysis and not outcome.fallback_used),
            })
            if guard.stopped:
                current["status"] = "hard_stop"
                current["accepted"] = False
                current["hardStopReason"] = guard.hard_stop_reason or "guard_stopped"
                report.update(status="stopped", errorType="AgentHardStop")
                report["stopReason"] = guard.hard_stop_reason or "guard_stopped"
                hard_stopped = True
                save()
                break
            if outcome.fallback_used:
                current["status"] = "rules_fallback"
                had_fallback = True
            elif outcome.tool_calls and any(
                call.get("status") == "not_requested" for call in outcome.tool_calls
            ):
                current["status"] = "model_stopped"
            elif not outcome.tool_calls and outcome.request_count == 1:
                current["status"] = "program_skipped_planning"
            else:
                current["status"] = "structural_checks_complete"
            save()
        if not hard_stopped:
            report["status"] = (
                "completed_with_rules_fallback"
                if had_fallback
                else "structural_checks_complete_human_review_pending"
            )
    except Exception as error:
        guard.stopped = True
        report.update(
            status="stopped",
            errorType=type(error).__name__,
            stopReason=guard.hard_stop_reason or str(error),
        )
    finally:
        settings.ai_per_report_input_token_limit = old_input_limit
        settings.ai_per_report_output_token_limit = old_output_limit
        try:
            save()
        except Exception as exc:
            guard.stopped = True
            # No report is returned and the CLI emits no success summary when
            # either durable destination cannot persist the final stopped state.
            raise SmokeStopped(
                "Agent final report persistence failed; batch cannot continue"
            ) from exc
    return report


def check_packet(packet: dict) -> None:
    if tuple(row["id"] for row in packet["cases"]) != CASE_IDS:
        raise SmokeStopped("Only the three reviewed synthetic cases are permitted")
    for relative, expected in packet["sourceHashes"].items():
        path = (ROOT / relative).resolve()
        if (
            not path.is_relative_to(ROOT)
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise SmokeStopped("Reviewed source changed; regenerate and review the packet")
    for row in packet["cases"]:
        if payload_hash(row["request"]) != row["requestSha256"]:
            raise SmokeStopped("Packet request hash mismatch")


def checked_prices(path: Path) -> tuple[Decimal, Decimal]:
    prices = json.loads(path.read_text(encoding="utf-8"))
    if (
        prices.get("verifiedDate") != datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        or prices.get("source") != "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
        or prices.get("model") != "deepseek-flash"
        or prices.get("currency") != "CNY"
    ):
        raise SmokeStopped("Current official price verification required")
    return Decimal(str(prices["inputYuanPerMillion"])), Decimal(str(prices["outputYuanPerMillion"]))


def claim_batch(state_root: Path, batch_id: str = BATCH_ID) -> Path:
    """Atomic claim shared across outputs/processes; never reset on restart or crash.

    This runner supports exactly one reviewed batch. A new output filename is not
    a new allowance. Reusing/removing this claim requires a separate human decision.
    """
    state_root.mkdir(parents=True, exist_ok=True)
    path = state_root / f"{batch_id}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump({"batch": batch_id, "status": "claimed_no_send_yet"}, stream)
    return path


async def execute(packet: dict, output: Path, prices: tuple[Decimal, Decimal]) -> dict:
    check_packet(packet)
    report = {
        "status": "started",
        "results": [],
        "humanReview": None,
        "attempts": [],
        "reservedYuan": "0",
        "syntheticOnly": True,
    }
    # Claim the new output before constructing a provider; preserve older runs.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream)
    guard = RequestGuard(*prices)
    batch_path = None

    def save():
        report.update(attempts=guard.attempts, reservedYuan=str(guard.reserved))
        content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        # Write the shared receipt first. A failed write prevents the next POST.
        if batch_path is not None:
            batch_path.write_text(content, encoding="utf-8")
        output.write_text(content, encoding="utf-8")

    guard.checkpoint = save
    try:
        batch_path = claim_batch(STATE_ROOT)
        report["batch"] = BATCH_ID
        save()
        provider = get_ai_provider()
        if not isinstance(provider, DeepSeekProvider):
            raise SmokeStopped("Current enabled provider must be official DeepSeek Flash")
        provider._max_attempts = 1
        provider._timeout = 30
        provider.durable_observer = guard  # Local-only receipt recording, no DB ledger.
        for row in packet["cases"]:
            case = row["syntheticInput"]
            files = [ProjectFileSnapshot(**item) for item in case["files"]]
            result = match_candidate(
                [
                    RequirementInput(
                        uuid5(NAMESPACE_URL, row["id"]), case["requirement"], case["skill"], 5
                    )
                ],
                parse_resume(case["resume"]),
                files,
            )
            contexts = build_evidence_contexts(enrich_evidence(result, files), max_evidence=2)
            guard.expected_hash, guard.case_id = row["requestSha256"], row["id"]
            current = {"id": row["id"], "accepted": None, "humanReview": None}
            report["results"].append(current)
            async with asyncio.timeout(45):
                analysis = await provider.analyze_evidence(
                    contexts=contexts, input_token_limit=20_000, output_token_limit=1_200
                )
            current["analysis"] = analysis.model_dump()
            validate_grounded_analysis(contexts, analysis)
            current["accepted"] = True  # Schema/grounding only, not human semantic quality.
            save()
        report["status"] = "structural_checks_complete_human_review_pending"
    except Exception as error:
        # Evaluation boundary records failure then stops the batch, never retries/relabels success.
        guard.stopped = True
        report.update(status="stopped", errorType=type(error).__name__)
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--prices", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--agent", action="store_true")
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    if args.agent:
        check_agent_packet(packet)
        if not args.live:
            print("OFFLINE: Agent packet/source hashes match; no provider or external request.")
            return 0
        if args.prices is None or args.output is None:
            parser.error("Agent live requires --prices and a new --output")
        report = asyncio.run(execute_agent(packet, args.output, checked_prices(args.prices)))
        print(json.dumps({
            "status": report["status"],
            "physicalRequests": len(report["attempts"]),
            "reservedYuan": report["reservedYuan"],
        }))
        return 0 if report["status"].startswith("structural_checks_complete") else 1
    check_packet(packet)
    if not args.live:
        print(
            "OFFLINE: packet/source hashes match; no provider constructed or external request made."
        )
        return 0
    if args.prices is None or args.output is None:
        parser.error(
            "Live mode requires --prices and a new --output after explicit user authorization"
        )
    report = asyncio.run(execute(packet, args.output, checked_prices(args.prices)))
    print(
        json.dumps(
            {
                "status": report["status"],
                "physicalRequests": len(report["attempts"]),
                "reservedYuan": report["reservedYuan"],
            }
        )
    )
    return 0 if report["status"].startswith("structural_checks_complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
