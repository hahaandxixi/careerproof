"""Opt-in synthetic verification app; never the production app entry point."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.agents.provider import DeepSeekProvider
from app.core.config import settings

MODEL = "deepseek-flash"
PROVIDER = "e2e-mock"


def validate_environment(run: str, database_url: str, storage: Path,
                         external_enabled: bool, provider: str) -> None:
    """Refuse production databases, remote hosts and any external AI mode."""
    parsed = urlsplit(database_url)
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", run)
        or parsed.scheme != "postgresql+asyncpg"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.path != f"/cp_e2e_{run}"
        or parsed.query or parsed.fragment
        or external_enabled or provider != "mock"
    ):
        raise ValueError("Synthetic verification requires an isolated local mock E2E environment")
    expected = Path(__file__).resolve().parents[1] / ".tmp" / "e2e-storage" / run
    if storage.resolve() != expected.resolve():
        raise ValueError("Synthetic verification storage must belong to this E2E run")


def synthetic_completion(request: httpx.Request) -> httpx.Response:
    """All responses and usage are authored synthetic fixtures, never receipts from a vendor."""
    payload = json.loads(request.content)
    context = json.loads(payload["messages"][-1]["content"])
    items = [{
        "requirementId": requirement["requirementId"],
        "visibleSupport": None,
        "informationGap": "合成核验建议：现有片段不能确认本人贡献及独立完成过程。",
        "verificationQuestions": ["请说明本人负责的部分，并演示相关操作。"],
        "nextStep": None, "nextStepReason": None, "citationIds": [],
    } for requirement in context["fixedReportRequirements"]]
    return httpx.Response(200, json={
        "id": "synthetic-e2e-verification", "model": MODEL,
        "choices": [{"message": {
            "role": "assistant", "content": json.dumps({"items": items}, ensure_ascii=False),
        }, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 80,
                  "total_tokens": 180, "prompt_cache_hit_tokens": 0,
                  "prompt_cache_miss_tokens": 100},
    })


class SyntheticVerificationProvider(DeepSeekProvider):
    name = PROVIDER

    def __init__(self):
        super().__init__(api_key="synthetic-local-only", base_url="https://api.deepseek.com",
                         model=MODEL, timeout_seconds=5,
                         transport=httpx.MockTransport(synthetic_completion), max_attempts=1)


def create_app():
    """Uvicorn --factory entry; apply fixture overrides only after fail-closed guards."""
    run = os.environ.get("E2E_SYNTHETIC_VERIFICATION_RUN", "")
    validate_environment(run, settings.database_url, settings.storage_base_dir,
                         settings.ai_external_enabled, settings.ai_provider)
    from app.main import app
    from app.services import application_verification

    application_verification._identity = lambda: (PROVIDER, MODEL)
    application_verification.get_ai_provider = SyntheticVerificationProvider
    return app
