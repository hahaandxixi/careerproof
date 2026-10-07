"""Strict, privacy-bounded token facts extracted before business JSON parsing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UsageReceipt:
    trusted: bool
    input_tokens: int | None
    output_tokens: int | None
    cache_hit_tokens: int | None
    raw: dict
    response_digest: str
    reason: str | None = None


def _count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _safe(value: object) -> object:
    # Invalid strings/containers can contain a model's business content or PII.
    # Their type is sufficient for reconciliation; never persist their value.
    if type(value) is int or value is None:
        return value
    return {"invalidType": type(value).__name__}


def parse_usage_receipt(payload: object) -> UsageReceipt:
    """Retain only usage counters and a digest of an opaque response identity.

    Missing/invalid counters yield None, distinct from a trustworthy zero.
    Business messages, arbitrary usage keys and literal response IDs never
    enter the receipt, its raw fields or its digest input.
    """
    body = payload if isinstance(payload, dict) else {}
    usage = body.get("usage")
    raw = {}
    if isinstance(usage, dict):
        for key in ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens"):
            if key in usage:
                raw[key] = _safe(usage[key])
        if "prompt_tokens_details" in usage:
            details = usage["prompt_tokens_details"]
            raw["prompt_tokens_details"] = (
                {"cached_tokens": _safe(details["cached_tokens"])}
                if isinstance(details, dict) and "cached_tokens" in details
                else {} if isinstance(details, dict) else _safe(details)
            )
    response_id = body.get("id")
    identity_hash = (
        hashlib.sha256(response_id.encode("utf-8")).hexdigest()
        if isinstance(response_id, str) else None
    )
    digest = hashlib.sha256(json.dumps(
        {"usage": raw, "responseIdentityHash": identity_hash},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()

    def unknown(reason: str) -> UsageReceipt:
        return UsageReceipt(False, None, None, None, raw, digest, reason)

    if not isinstance(usage, dict):
        return unknown("missing_usage")
    inputs = _count(usage.get("prompt_tokens"))
    outputs = _count(usage.get("completion_tokens"))
    if inputs is None:
        return unknown("invalid_prompt_tokens")
    if outputs is None:
        return unknown("invalid_completion_tokens")
    cache_values = []
    if "prompt_tokens_details" in usage:
        details = usage["prompt_tokens_details"]
        if not isinstance(details, dict):
            return unknown("invalid_cache_details")
        if "cached_tokens" in details:
            cache_values.append(_count(details["cached_tokens"]))
    if "prompt_cache_hit_tokens" in usage:
        cache_values.append(_count(usage["prompt_cache_hit_tokens"]))
    if any(value is None for value in cache_values):
        return unknown("invalid_cache_tokens")
    if len(set(cache_values)) > 1:
        return unknown("conflicting_cache_tokens")
    cache = cache_values[0] if cache_values else 0
    if cache > inputs:
        return unknown("cache_exceeds_input")
    return UsageReceipt(True, inputs, outputs, cache, raw, digest)
