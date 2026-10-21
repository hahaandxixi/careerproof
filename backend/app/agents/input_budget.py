"""Canonical local estimate for an outgoing model request.

The value is a UTF-8 byte estimate of the full serialized request plus a
deliberate safety margin. It is not a provider-billed token count.
"""
from __future__ import annotations

import json

WIRE_SAFETY_MARGIN_BYTES = 1024


def wire_payload_bytes(request: dict) -> int:
    """Return the UTF-8 byte length of the canonical request JSON."""
    return len(
        json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
    )


def estimate_wire_input_bytes(request: dict) -> int:
    """Conservative request admission bound used before any physical POST.

    The 1,024-byte margin is an explicit framing/escaping reserve. It is not a
    tokenizer estimate and does not duplicate tool schemas: the full request,
    including tools, is already serialized above.
    """
    return wire_payload_bytes(request) + WIRE_SAFETY_MARGIN_BYTES
