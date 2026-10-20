"""Executor-level regressions: real provider/workflow, synthetic MockTransport only."""

import asyncio
import json
import subprocess
import sys
import textwrap
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.agents.provider import DeepSeekProvider
from app.core.config import settings
from app.tests.test_agent_evidence_smoke import answer, packet
from evals import bounded_evidence_smoke as smoke


def setup_batch(monkeypatch, tmp_path, error_status=None, error_stage="planning"):
    data, calls, holder = packet(), [], {}

    def handler(request):
        guard = holder["guard"]
        body = json.loads(request.content)
        case = next(c for c in data["cases"] if c["id"] == guard.case_id)
        calls.append((request.method, guard.case_id, guard.stage))
        usage = {"prompt_tokens": 100, "completion_tokens": 10}
        planning = "tools" in body
        if error_status and (error_stage == "planning" or not planning):
            return httpx.Response(
                error_status, json={"error": {"message": "synthetic"}, "usage": usage}
            )
        content = "" if planning else json.dumps(answer(case, "R1-E1"))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}], "usage": usage}
        )

    provider = DeepSeekProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=1,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    original_guard = smoke.AgentRequestGuard

    def capture_guard(*args, **kwargs):
        holder["guard"] = original_guard(*args, **kwargs)
        return holder["guard"]

    monkeypatch.setattr(smoke, "AgentRequestGuard", capture_guard)
    monkeypatch.setattr(smoke, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(smoke, "STATE_ROOT", tmp_path / "isolated-claim")
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    return data, calls, holder


def fail_receipt_write(monkeypatch, output, persistent):
    original = Path.write_text
    fault = {"fired": False}

    def write(path, content, *args, **kwargs):
        if path == output:
            attempts = json.loads(content).get("attempts", [])
            receipt = any(a["status"] == "receipt_observed" for a in attempts)
            if (receipt and not fault["fired"]) or (persistent and fault["fired"]):
                fault["fired"] = True
                raise OSError("synthetic receipt disk failure")
        return original(path, content, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write)
    return fault


def test_receipt_checkpoint_failure_stops_real_executor_after_one_post(monkeypatch, tmp_path):
    data, calls, holder = setup_batch(monkeypatch, tmp_path)
    output = tmp_path / "receipt.json"
    fault = fail_receipt_write(monkeypatch, output, persistent=False)
    report = asyncio.run(smoke.execute_agent(data, output, (Decimal(2), Decimal(8))))
    assert fault["fired"]
    assert calls == [("POST", "AG-01", "planning_1")]
    assert holder["guard"].stopped
    assert report["status"] == "stopped"
    assert report["stopReason"] == "receipt_checkpoint_failed"
    assert len(report["results"]) == 1
    assert report["results"][0]["status"] == "hard_stop"
    assert report["results"][0]["accepted"] is False
    assert report["humanReview"] is None
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "stopped"


def test_final_log_write_failure_exits_without_success_summary(tmp_path):
    code = textwrap.dedent("""
        import json, sys
        from pathlib import Path
        from decimal import Decimal
        import pytest
        from app.tests.test_agent_smoke_hard_stop import setup_batch, fail_receipt_write
        from evals import bounded_evidence_smoke as smoke
        root = Path(sys.argv[1])
        patch = pytest.MonkeyPatch()
        data, calls, holder = setup_batch(patch, root)
        output = root / "unsaved.json"
        fail_receipt_write(patch, output, persistent=True)
        patch.setattr(smoke, "checked_prices", lambda _: (Decimal(2), Decimal(8)))
        packet_path = root / "packet.json"
        packet_path.write_text(json.dumps(data), encoding="utf-8")
        sys.argv = ["smoke", "--agent", "--live", "--packet", str(packet_path),
                    "--output", str(output), "--prices", str(root / "synthetic-price.json")]
        try:
            smoke.main()
        finally:
            print(json.dumps({"calls": calls, "stopped": holder["guard"].stopped}))
    """)
    child = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        cwd=smoke.ROOT / "backend",
        capture_output=True,
        timeout=30,
    )
    assert child.returncode != 0
    assert b"Agent final report persistence failed" in child.stderr
    assert b"structural_checks_complete" not in child.stdout
    trace = json.loads(child.stdout.decode().splitlines()[-1])
    assert trace == {"calls": [["POST", "AG-01", "planning_1"]], "stopped": True}
    output = tmp_path / "unsaved.json"
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "started"


@pytest.mark.parametrize("status", [400, 401])
@pytest.mark.parametrize("stage,expected_posts", [("planning", 1), ("analysis", 2)])
def test_nonretry_http_error_with_trusted_usage_stops_batch(
    monkeypatch, tmp_path, status, stage, expected_posts
):
    data, calls, holder = setup_batch(monkeypatch, tmp_path, status, stage)
    output = tmp_path / "http-error.json"
    report = asyncio.run(smoke.execute_agent(data, output, (Decimal(2), Decimal(8))))
    assert len(calls) == expected_posts and all(c[0:2] == ("POST", "AG-01") for c in calls)
    assert holder["guard"].stopped
    assert report["status"] == "stopped"
    assert report["stopReason"] == f"provider_http_{status}"
    assert len(report["results"]) == 1
    assert report["results"][0]["status"] == "hard_stop"
    assert report["results"][0]["accepted"] is False
    assert all(a["response"]["usage"]["prompt_tokens"] == 100 for a in report["attempts"])
