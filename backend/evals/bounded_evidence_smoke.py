"""Opt-in, three-request synthetic evidence smoke; no DB, retries or repair calls."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.agents.contracts import validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.provider import (
    DeepSeekProvider,
    conservative_input_token_estimate,
    get_ai_provider,
)
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume

ROOT = Path(__file__).resolve().parents[2]
CASE_IDS = ("route-body", "empty-route", "contradictory-return")
BATCH_ID = "current-smoke-20261018-three-cases"
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


def claim_batch(state_root: Path) -> Path:
    """Atomic claim shared across outputs/processes; never reset on restart or crash.

    This runner supports exactly one reviewed batch. A new output filename is not
    a new allowance. Reusing/removing this claim requires a separate human decision.
    """
    state_root.mkdir(parents=True, exist_ok=True)
    path = state_root / f"{BATCH_ID}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump({"batch": BATCH_ID, "status": "claimed_no_send_yet"}, stream)
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
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
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
