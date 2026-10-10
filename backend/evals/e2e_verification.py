"""Opt-in synthetic verification app; never the production app entry point."""

from __future__ import annotations

import asyncio
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
CONTROL_NAME = "synthetic-verification-control.json"


def read_control(path: Path | None) -> dict:
    """A fixed run-local file controls mock responses; never an HTTP endpoint."""
    if path is None:
        return {"mode": "known", "delaySeconds": 0}
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Synthetic control cannot use a linked path")
    if not path.exists():
        return {"mode": "known", "delaySeconds": 0}
    if path.name != CONTROL_NAME or not path.is_file() or path.stat().st_size > 1024:
        raise ValueError("Invalid synthetic control file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) - {"mode", "delaySeconds"}:
        raise ValueError("Invalid synthetic control fields")
    mode = value.get("mode")
    delay = value.get("delaySeconds", 0)
    if (mode not in {"known", "delay", "unknown", "failure"}
            or type(delay) not in {int, float} or not 0 <= delay <= 15
            or (mode != "delay" and delay != 0)):
        raise ValueError("Invalid synthetic mode or bounded delay")
    return {"mode": mode, "delaySeconds": delay}


async def controlled_completion(
    request: httpx.Request, control_path: Path | None,
) -> httpx.Response:
    # Read once per physical request; later file edits cannot change an in-flight result.
    control = read_control(control_path)
    if control["mode"] == "delay":
        await asyncio.sleep(control["delaySeconds"])
    if control["mode"] == "failure":
        return httpx.Response(503, json={"error": {"message": "synthetic fixture failure"}})
    response = synthetic_completion(request)
    if control["mode"] == "unknown":
        payload = response.json()
        del payload["usage"]
        return httpx.Response(200, json=payload)
    return response


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

    def __init__(self, control_path: Path | None = None):
        async def handler(request):
            return await controlled_completion(request, control_path)

        super().__init__(api_key="synthetic-local-only", base_url="https://api.deepseek.com",
                         model=MODEL, timeout_seconds=20,
                         transport=httpx.MockTransport(handler), max_attempts=1)


def create_app():
    """Uvicorn --factory entry; apply fixture overrides only after fail-closed guards."""
    run = os.environ.get("E2E_SYNTHETIC_VERIFICATION_RUN", "")
    validate_environment(run, settings.database_url, settings.storage_base_dir,
                         settings.ai_external_enabled, settings.ai_provider)
    from app.main import app
    from app.services import application_verification

    control_path = settings.storage_base_dir / CONTROL_NAME
    read_control(control_path)
    application_verification._identity = lambda: (PROVIDER, MODEL)
    application_verification.get_ai_provider = lambda: SyntheticVerificationProvider(control_path)
    return app
