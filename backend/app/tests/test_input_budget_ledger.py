import json

from app.agents.input_budget import (
    WIRE_SAFETY_MARGIN_BYTES,
    estimate_wire_input_bytes,
    wire_payload_bytes,
)


def test_wire_estimate_is_utf8_bytes_plus_explicit_margin():
    request = {
        "model": "deepseek-flash",
        "messages": [{"role": "user", "content": "校园活动报名"}],
        "tools": [{"type": "function", "function": {"name": "retrieve_more_evidence"}}],
    }

    body = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
    characters = len(json.dumps(request, ensure_ascii=False, allow_nan=False))

    assert wire_payload_bytes(request) == len(body)
    assert estimate_wire_input_bytes(request) == len(body) + WIRE_SAFETY_MARGIN_BYTES
    assert len(body) > characters
    assert WIRE_SAFETY_MARGIN_BYTES == 1024


def test_historical_42k_and_60k_arithmetic_is_explicit():
    planning = 10_653
    analysis = 38_846
    total = planning + analysis

    assert total == 49_499
    assert total > 42_000
    assert total < 60_000
    assert 60_000 - total == 10_501
