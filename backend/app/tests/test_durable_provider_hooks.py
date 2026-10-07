import asyncio

import httpx
import pytest

from app.agents.provider import DeepSeekProvider, ProviderReceiptPersistenceError


class Observer:
    def __init__(self, *, admission_error=None, receipt_error=None):
        self.admission_error = admission_error
        self.receipt_error = receipt_error
        self.events = []

    async def before_send(self, request):
        self.events.append(("intent", request["max_tokens"]))
        if self.admission_error:
            raise self.admission_error
        return len([event for event in self.events if event[0] == "intent"])

    async def after_response(self, attempt_id, payload, latency):
        self.events.append(("receipt", attempt_id, payload, latency))
        if self.receipt_error:
            raise self.receipt_error

    async def on_failure(self, attempt_id, reason):
        self.events.append(("failure", attempt_id, reason))


def make_provider(handler, observer):
    provider = DeepSeekProvider(
        api_key="synthetic-only", base_url="https://api.deepseek.com",
        model="deepseek-flash", timeout_seconds=1,
        transport=httpx.MockTransport(handler), max_attempts=3,
    )
    provider.durable_observer = observer
    provider._retry_delay = lambda response, attempt: 0
    return provider


async def test_failed_durable_admission_sends_nothing():
    calls = []
    observer = Observer(admission_error=httpx.NetworkError("database unavailable"))
    provider = make_provider(lambda request: calls.append(request), observer)
    with pytest.raises(httpx.NetworkError):
        await provider._completion({"max_tokens": 20})
    assert calls == []
    assert observer.events == [("intent", 20)]


@pytest.mark.parametrize("error", [RuntimeError("write failed"), httpx.NetworkError("db failed")])
async def test_receipt_write_failure_never_resends_http(error):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"usage": {"prompt_tokens": 7, "completion_tokens": 2}})

    observer = Observer(receipt_error=error)
    provider = make_provider(handler, observer)
    with pytest.raises(ProviderReceiptPersistenceError) as caught:
        await provider._completion({"max_tokens": 20})
    assert caught.value.__cause__ is error
    assert len(calls) == 1
    assert [event[0] for event in observer.events] == ["intent", "receipt"]


async def test_each_physical_retry_has_its_own_receipt():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, json={"attempt": len(calls)})

    observer = Observer()
    payload, _ = await make_provider(handler, observer)._completion({"max_tokens": 20})
    assert payload == {"attempt": 2}
    assert [event[:2] for event in observer.events] == [
        ("intent", 20), ("receipt", 1), ("failure", 1),
        ("intent", 20), ("receipt", 2),
    ]
    assert len(calls) == 2


async def test_http_error_receipt_precedes_status_rejection():
    observer = Observer()
    payload = {"usage": {"prompt_tokens": 7, "completion_tokens": 2}}
    provider = make_provider(lambda request: httpx.Response(403, json=payload), observer)
    with pytest.raises(httpx.HTTPStatusError):
        await provider._completion({"max_tokens": 20})
    assert observer.events[1][0:3] == ("receipt", 1, payload)
    assert len(observer.events) == 2


async def test_invalid_response_json_records_unknown_receipt_before_parse_error():
    observer = Observer()
    provider = make_provider(lambda request: httpx.Response(200, text="invalid JSON"), observer)
    with pytest.raises(ValueError):
        await provider._completion({"max_tokens": 20})
    assert observer.events[1][0:3] == ("receipt", 1, {})
    assert len(observer.events) == 2


async def test_cancelled_send_records_ambiguous_attempt_without_retry():
    calls = []

    async def handler(request):
        calls.append(request)
        raise asyncio.CancelledError()

    observer = Observer()
    with pytest.raises(asyncio.CancelledError):
        await make_provider(handler, observer)._completion({"max_tokens": 20})
    assert observer.events == [("intent", 20), ("failure", 1, "cancelled")]
    assert len(calls) == 1
