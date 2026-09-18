"""Validate DeepSeek locally; --live sends one explicit synthetic request."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from app.agents.provider import DeepSeekProvider
from app.core.config import settings


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Send one synthetic API request")
    args = parser.parse_args()
    key = settings.deepseek_api_key
    if key is None or not key.get_secret_value().strip():
        print("DEEPSEEK_API_KEY is empty. Fill backend/.env locally; do not share the key.")
        return 1
    try:
        provider = DeepSeekProvider(
            api_key=key.get_secret_value(),
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
            max_attempts=1,
        )
        if not args.live:
            print("Local configuration OK. No API request sent; billing not verified.")
            return 0
        started = perf_counter()
        try:
            async with asyncio.timeout(settings.ai_workflow_timeout_seconds):
                result = await provider.summarize_match(
                    deterministic_summary="合成材料包含接口片段；未执行，不能证明本人能力。",
                    job_title="合成后端岗位",
                    candidate_name="合成样本",
                )
            report = {
                "generatedAt": datetime.now(UTC).isoformat(),
                "case": "synthetic-deepseek-connectivity",
                "connection": "ok",
                "provider": provider.name,
                "model": provider.model,
                "jsonValidated": bool(result.summary),
                "attempts": 1,
                "usage": provider.last_usage.model_dump() if provider.last_usage else None,
                "elapsedMs": round((perf_counter() - started) * 1000),
                "billingVerified": False,
                "syntheticDataOnly": True,
            }
        except Exception as exc:
            report = {
                "generatedAt": datetime.now(UTC).isoformat(),
                "case": "synthetic-deepseek-connectivity",
                "connection": "failed",
                "provider": provider.name,
                "model": provider.model,
                "errorType": type(exc).__name__,
                "elapsedMs": round((perf_counter() - started) * 1000),
                "billingVerified": False,
                "syntheticDataOnly": True,
            }
        output = Path("evals") / f"deepseek-connectivity-{datetime.now():%Y%m%d-%H%M%S}.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({**report, "output": str(output)}, ensure_ascii=False))
        if report["connection"] != "ok":
            return 1
        return 0
    except Exception as exc:
        # Never print the key, request headers, response body, or transport details.
        print(json.dumps({"connection": "failed", "errorType": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
