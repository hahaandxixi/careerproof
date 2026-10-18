"""Prepare exact production requests through MockTransport; never sends externally."""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402

from app.agents.evidence_workflow import build_evidence_contexts  # noqa: E402
from app.agents.provider import (  # noqa: E402
    EVIDENCE_PROMPT_VERSION,
    DeepSeekProvider,
    conservative_input_token_estimate,
)
from app.tools.code_analyzer import ProjectFileSnapshot  # noqa: E402
from app.tools.evidence_context import enrich_evidence  # noqa: E402
from app.tools.matcher import RequirementInput, match_candidate  # noqa: E402
from app.tools.resume_parser import parse_resume  # noqa: E402

CASE_IDS = ("route-body", "empty-route", "contradictory-return")
INPUT_LIMIT = 20_000
OUTPUT_LIMIT = 1_200


class PreviewCaptured(Exception):
    """Interrupt before a model response; no fabricated analysis is produced."""


async def prepare() -> dict:
    source = ROOT / "backend/evals/evidence-trust-cases.json"
    cases = json.loads(source.read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in cases}
    rows = []
    for case_id in CASE_IDS:
        case = by_id[case_id]
        files = [ProjectFileSnapshot(**item) for item in case["files"]]
        result = match_candidate(
            [RequirementInput(uuid5(NAMESPACE_URL, case_id), case["requirement"], case["skill"], 5)],
            parse_resume(case["resume"]),
            files,
        )
        contexts = build_evidence_contexts(enrich_evidence(result, files), max_evidence=2)
        captured = []

        def intercept(request: httpx.Request) -> httpx.Response:
            # Store JSON only: never store headers, including the dummy Authorization.
            captured.append(json.loads(request.content))
            raise PreviewCaptured

        provider = DeepSeekProvider(
            api_key="offline-preview-not-a-credential",
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout_seconds=30,
            max_attempts=1,
            transport=httpx.MockTransport(intercept),
        )
        try:
            await provider.analyze_evidence(
                contexts=contexts, input_token_limit=INPUT_LIMIT, output_token_limit=OUTPUT_LIMIT
            )
        except PreviewCaptured:
            pass
        if len(captured) != 1:
            raise AssertionError(f"Expected one intercepted request for {case_id}")
        payload = captured[0]
        bound = conservative_input_token_estimate(payload["messages"])
        if bound > INPUT_LIMIT or payload["max_tokens"] > OUTPUT_LIMIT:
            raise AssertionError("Production payload exceeds proposed authorization limits")
        rows.append({
            "id": case_id,
            "syntheticInput": case,
            "request": payload,
            "conservativeInputBound": bound,
            "requestSha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
            "output": None,
            "humanReview": None,
        })
    paths = (
        "backend/evals/evidence-trust-cases.json",
        "backend/app/agents/provider.py",
        "backend/app/agents/evidence_workflow.py",
        "backend/app/agents/contracts.py",
        "backend/app/tools/matcher.py",
        "backend/app/tools/evidence_context.py",
    )
    return {
        "status": "offline_prepared_awaiting_external_authorization",
        "externalRequests": 0,
        "mockTransportCalls": len(rows),
        "promptVersion": EVIDENCE_PROMPT_VERSION,
        "plannedPhysicalRequestLimitIncludingRetries": 3,
        "inputUpperBoundPerRequest": INPUT_LIMIT,
        "outputLimitPerRequest": OUTPUT_LIMIT,
        "proposedTotalYuanCeiling": 1,
        "pricingVerified": False,
        "liveExecutionReady": False,
        "sourceHashes": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
        "cases": rows,
        "stopBeforeLiveUnless": [
            "User approves these exact synthetic inputs and official DeepSeek destination",
            "Current official prices establish the token caps fit within the approved fee ceiling",
            "Physical-request guard counts before POST; no retries or repair beyond three total",
            "Missing or untrusted usage, invalid citations, or material contradictions stop the batch",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = asyncio.run(prepare())
    # Exclusive creation preserves earlier packets; no live mode is implemented here.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(packet, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({
        "externalRequests": packet["externalRequests"],
        "cases": [{"id": row["id"], "inputBound": row["conservativeInputBound"],
                   "maxOutput": row["request"]["max_tokens"]} for row in packet["cases"]],
    }))
