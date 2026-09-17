"""Local preflight by default; --live makes one explicit synthetic model request."""

import argparse
import asyncio
import json

from app.agents.provider import ZhipuProvider
from app.core.config import settings


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Send one synthetic API request")
    args = parser.parse_args()
    key = settings.zhipu_api_key
    if key is None or not key.get_secret_value().strip():
        print("ZHIPU_API_KEY is empty. Fill backend/.env locally; do not share the key.")
        return 1
    try:
        provider = ZhipuProvider(
            api_key=key.get_secret_value(),
            base_url=settings.zhipu_base_url,
            model=settings.zhipu_model,
            timeout_seconds=settings.zhipu_timeout_seconds,
            max_attempts=1,
        )
        if not args.live:
            print("Local configuration OK. No API request sent; pricing/billing not verified.")
            return 0
        async with asyncio.timeout(settings.ai_workflow_timeout_seconds):
            result = await provider.summarize_match(
                deterministic_summary="合成代码包含健康检查函数；尚未执行，不能证明本人能力。",
                job_title="合成后端岗位",
                candidate_name="合成样本",
            )
        print(
            json.dumps(
                {
                    "connection": "ok",
                    "model": provider.model,
                    "jsonValidated": bool(result.summary),
                    "attempts": 1,
                    "billingVerified": False,
                    "next": "Check the platform bill is zero before enabling project calls.",
                }
            )
        )
        return 0
    except Exception as exc:
        # Never print the key, headers, response body, or transport exception string.
        print(json.dumps({"connection": "failed", "errorType": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
