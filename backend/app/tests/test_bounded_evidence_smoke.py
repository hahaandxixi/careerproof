import asyncio
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.agents.provider import DeepSeekProvider
from evals import bounded_evidence_smoke as smoke


def request():
    return {
        "model": "deepseek-flash",
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": "synthetic"}],
        "max_tokens": 1200,
    }


def guard_for(payload=None, input_price="2", output_price="8"):
    guard = smoke.RequestGuard(Decimal(input_price), Decimal(output_price))
    guard.expected_hash = smoke.payload_hash(payload or request())
    return guard


def test_fourth_physical_request_rejected_and_worst_price_reserved():
    async def run():
        guard = guard_for()
        for _ in range(3):
            await guard.before_send(request())
        with pytest.raises(smoke.SmokeStopped, match="allowance"):
            await guard.before_send(request())
        assert len(guard.attempts) == 3
        assert guard.reserved == Decimal("0.1488")

    asyncio.run(run())


@pytest.mark.parametrize(
    "change",
    [
        {"max_tokens": 1201},
        {"max_tokens": True},
        {"thinking": {"type": "enabled"}},
        {"model": "other"},
        {"messages": [{"role": "user", "content": "x" * 20001}]},
    ],
)
def test_bad_request_rejected_before_any_reservation(change):
    async def run():
        payload = {**request(), **change}
        guard = guard_for(payload)
        with pytest.raises(smoke.SmokeStopped):
            await guard.before_send(payload)
        assert not guard.attempts and guard.reserved == 0

    asyncio.run(run())


def test_fee_or_changed_packet_rejected_before_send():
    async def run():
        for guard in (guard_for(input_price="100"), guard_for()):
            if guard.input_price != Decimal("100"):
                guard.expected_hash = "changed"
            with pytest.raises(smoke.SmokeStopped):
                await guard.before_send(request())
            assert not guard.attempts

    asyncio.run(run())


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"prompt_tokens": True, "completion_tokens": 1},
        {"prompt_tokens": 1, "completion_tokens": 1201},
        {"prompt_tokens": 20001, "completion_tokens": 1},
    ],
)
def test_bad_receipt_blocks_next_request_and_keeps_reservation(usage):
    async def run():
        guard = guard_for()
        attempt = await guard.before_send(request())
        with pytest.raises(smoke.SmokeStopped):
            await guard.after_response(attempt, {"usage": usage}, 1)
        with pytest.raises(smoke.SmokeStopped):
            await guard.before_send(request())
        assert len(guard.attempts) == 1 and guard.reserved == Decimal("0.0496")

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["http", "timeout"])
def test_real_provider_retry_cannot_bypass_guard(failure):
    async def run():
        calls = []

        def reply(req):
            calls.append(req)
            if failure == "timeout":
                raise httpx.ReadTimeout("synthetic timeout", request=req)
            return httpx.Response(
                503,
                json={"usage": {"prompt_tokens": 1, "completion_tokens": 0}},
                headers={"Retry-After": "0"},
            )

        provider = DeepSeekProvider(
            api_key="synthetic-not-real",
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout_seconds=1,
            max_attempts=3,
            transport=httpx.MockTransport(reply),
        )
        guard = guard_for()
        provider.durable_observer = guard
        with pytest.raises(smoke.SmokeStopped):
            await provider._completion(request())
        assert len(calls) == len(guard.attempts) == 1

    asyncio.run(run())


def test_checkpoint_failure_prevents_real_provider_http():
    async def run():
        def no_record():
            raise OSError("synthetic disk error")

        guard = guard_for()
        guard.checkpoint = no_record
        provider = DeepSeekProvider(
            api_key="synthetic-not-real",
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout_seconds=1,
            transport=httpx.MockTransport(lambda _: pytest.fail("HTTP reached")),
        )
        provider.durable_observer = guard
        with pytest.raises(OSError):
            await provider._completion(request())

    asyncio.run(run())


def packet_path():
    return (
        smoke.ROOT
        / "docs/evidence/20261017-task70-semantic-review-packet"
        / "current-smoke-preflight-20261018.json"
    )


def test_old_executor_unknown_usage_stops_once_with_synthetic_fixture(monkeypatch, tmp_path):
    payload = request()

    def old_case(case_id):
        return {
            "id": case_id,
            "syntheticInput": {
                "requirement": "Python 业务处理",
                "skill": "Python",
                "resume": "熟悉 Python",
                "files": [{"path": "app.py", "content": "def handle():\n    return 1\n"}],
            },
            "request": payload,
            "requestSha256": smoke.payload_hash(payload),
        }

    packet = {"sourceHashes": {}, "cases": [old_case(case_id) for case_id in smoke.CASE_IDS]}
    calls = []

    class FixedProvider(DeepSeekProvider):
        async def analyze_evidence(self, **kwargs):
            return await self._completion(payload)

    provider = FixedProvider(
        api_key="synthetic-not-real",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(
            lambda req: (
                calls.append(req)
                or httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
            )
        ),
    )
    monkeypatch.setattr(smoke, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(smoke, "STATE_ROOT", tmp_path / "old-state")
    report = asyncio.run(
        smoke.execute(packet, tmp_path / "old-result.json", (Decimal(2), Decimal(8)))
    )
    assert report["status"] == "stopped"
    assert report["errorType"] == "ProviderReceiptPersistenceError"
    assert len(report["results"]) == 1
    assert report["attempts"][0]["status"] == "usage_untrusted"
    assert len(calls) == 1
    assert "synthetic-not-real" not in (tmp_path / "old-result.json").read_text()
    with pytest.raises(FileExistsError):
        asyncio.run(smoke.execute(packet, tmp_path / "old-result.json", (Decimal(2), Decimal(8))))
    replay = asyncio.run(
        smoke.execute(packet, tmp_path / "old-replay.json", (Decimal(2), Decimal(8)))
    )
    assert replay["status"] == "stopped"
    assert replay["errorType"] == "FileExistsError"
    assert len(calls) == 1


def test_historical_packet_is_rejected_after_source_change():
    with pytest.raises(smoke.SmokeStopped, match="source changed"):
        smoke.check_packet(json.loads(packet_path().read_text(encoding="utf-8")))


def test_offline_cli_never_constructs_provider(tmp_path, monkeypatch):
    packet = {
        "sourceHashes": {},
        "cases": [
            {
                "id": case_id,
                "request": request(),
                "requestSha256": smoke.payload_hash(request()),
            }
            for case_id in smoke.CASE_IDS
        ],
    }
    path = tmp_path / "synthetic-offline.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    monkeypatch.setattr(smoke, "get_ai_provider", lambda: pytest.fail("Provider constructed"))
    monkeypatch.setattr("sys.argv", ["smoke", "--packet", str(path)])
    assert smoke.main() == 0


def test_stale_prices_rejected(tmp_path):
    price = tmp_path / "prices.json"
    price.write_text(json.dumps({"verifiedDate": "2020-01-01"}), encoding="utf-8")
    with pytest.raises(smoke.SmokeStopped):
        smoke.checked_prices(Path(price))


def test_two_independent_processes_cannot_claim_same_batch(tmp_path):
    code = (
        "from pathlib import Path; import sys; "
        "from evals.bounded_evidence_smoke import claim_batch; "
        "claim_batch(Path(sys.argv[1]))"
    )
    children = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(tmp_path / "shared")],
            cwd=smoke.ROOT / "backend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = [child.communicate(timeout=15) for child in children]
    assert sorted(child.returncode for child in children) == [0, 1]
    assert sum(b"FileExistsError" in stderr for _, stderr in results) == 1
    assert (tmp_path / "shared" / f"{smoke.BATCH_ID}.json").exists()


def test_concurrent_admission_never_exceeds_three():
    async def run():
        guard = guard_for()
        results = await asyncio.gather(
            *(guard.before_send(request()) for _ in range(8)), return_exceptions=True
        )
        assert sum(isinstance(value, smoke.SmokeStopped) for value in results) == 5
        assert len(guard.attempts) == 3 and guard.reserved == Decimal("0.1488")

    asyncio.run(run())


def test_trusted_receipt_does_not_refund_request_allowance():
    async def run():
        guard = guard_for()
        for _ in range(3):
            attempt = await guard.before_send(request())
            await guard.after_response(
                attempt, {"usage": {"prompt_tokens": 1000, "completion_tokens": 200}}, 5
            )
        assert all(row["status"] == "receipt_observed" for row in guard.attempts)
        with pytest.raises(smoke.SmokeStopped):
            await guard.before_send(request())
        assert guard.reserved == Decimal("0.1488")

    asyncio.run(run())
