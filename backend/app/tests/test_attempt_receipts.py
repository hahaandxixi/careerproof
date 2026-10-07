"""A provider receipt is a token fact, never a copy of its business response."""

import json

import pytest

from app.agents.attempt_receipts import parse_usage_receipt


def payload(**usage):
    return {"id": "synthetic-response", "usage": usage}


def test_zero_is_known_but_missing_is_unknown():
    zero = parse_usage_receipt(payload(prompt_tokens=0, completion_tokens=0))
    assert zero.trusted and zero.input_tokens == zero.output_tokens == 0
    assert zero.cache_hit_tokens == 0
    missing = parse_usage_receipt({"id": "synthetic-response"})
    assert not missing.trusted and missing.input_tokens is None
    assert missing.reason == "missing_usage"


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens"])
@pytest.mark.parametrize("value", [None, True, -1, 1.5, "12", [], {}])
def test_invalid_counts_never_become_billable_zero(field, value):
    usage = {"prompt_tokens": 12, "completion_tokens": 5, field: value}
    receipt = parse_usage_receipt(payload(**usage))
    assert not receipt.trusted
    assert receipt.input_tokens is None and receipt.output_tokens is None
    assert receipt.reason == f"invalid_{field}"


@pytest.mark.parametrize("cache", [0, 4, 12])
def test_nested_and_deepseek_cache_fields_are_supported(cache):
    for extra in (
        {"prompt_tokens_details": {"cached_tokens": cache}},
        {"prompt_cache_hit_tokens": cache},
    ):
        receipt = parse_usage_receipt(payload(prompt_tokens=12, completion_tokens=5, **extra))
        assert receipt.trusted and receipt.cache_hit_tokens == cache
        assert receipt.input_tokens == 12 and receipt.output_tokens == 5


@pytest.mark.parametrize("cache", [True, -1, 1.5, "4", 13])
def test_invalid_or_impossible_cache_cannot_claim_known_usage(cache):
    receipt = parse_usage_receipt(payload(
        prompt_tokens=12, completion_tokens=5,
        prompt_tokens_details={"cached_tokens": cache},
    ))
    assert not receipt.trusted and receipt.cache_hit_tokens is None


def test_conflicting_cache_fields_are_not_silently_selected():
    receipt = parse_usage_receipt(payload(
        prompt_tokens=12, completion_tokens=5, prompt_cache_hit_tokens=3,
        prompt_tokens_details={"cached_tokens": 4},
    ))
    assert not receipt.trusted and receipt.reason == "conflicting_cache_tokens"


def test_receipt_does_not_copy_response_id_business_content_or_invalid_strings():
    secret = "synthetic-private-contact@example.invalid"
    body = {
        "id": secret,
        "choices": [{"message": {"content": secret}}],
        "usage": {"prompt_tokens": secret, "completion_tokens": 5, "other": secret},
    }
    receipt = parse_usage_receipt(body)
    serialized = json.dumps(receipt.raw, allow_nan=False)
    assert secret not in serialized and "choices" not in serialized and "other" not in serialized
    assert len(receipt.response_digest) == 64 and secret not in receipt.response_digest
    assert receipt.raw["prompt_tokens"] == {"invalidType": "str"}


def test_raw_receipt_is_detached_and_nan_is_safe_to_persist():
    body = payload(prompt_tokens=12, completion_tokens=5,
                   prompt_tokens_details={"cached_tokens": float("nan")})
    receipt = parse_usage_receipt(body)
    assert not receipt.trusted
    json.dumps(receipt.raw, allow_nan=False)
    body["usage"]["prompt_tokens_details"]["cached_tokens"] = 1
    assert receipt.raw["prompt_tokens_details"]["cached_tokens"] == {"invalidType": "float"}


def test_digest_changes_for_distinct_receipts_without_recording_business_text():
    first = parse_usage_receipt(payload(prompt_tokens=12, completion_tokens=5))
    changed = parse_usage_receipt(payload(prompt_tokens=12, completion_tokens=6))
    assert first.response_digest != changed.response_digest
    repeated = parse_usage_receipt(payload(prompt_tokens=12, completion_tokens=5))
    assert first.response_digest == repeated.response_digest
