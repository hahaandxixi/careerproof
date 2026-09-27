"""Bounded credential-shape filtering for explicitly authorized MCP exports.

This is not a universal secret detector. Encoded/unknown formats and unlabeled
fragments may not be recognized; source records and hashes remain unchanged.
"""

import re

MARKER = "[redacted credential]"
_KEY = (
    r"(?:[A-Za-z][A-Za-z0-9_-]*[_-])?"
    r"(?:api[_-]?key|password|passwd|pwd|secret(?:[_-]?key)?|token|"
    r"access[_-]?key(?:[_-]?id)?|private[_-]?key|authorization)"
)
_SENSITIVE_KEY = re.compile(_KEY, re.I)
# Quoted values include whitespace and escaped quotes. Unterminated source
# excerpts fail closed through their end rather than exposing the remaining value.
_LITERAL = (
    r'(?:(?:[rubf]{1,2})?(?:"{3}[\s\S]*?(?:"{3}|\Z)|'
    r"\x27{3}[\s\S]*?(?:\x27{3}|\Z)|"
    r'"(?:\\[\s\S]|[^"\\])*(?:"|\\?\Z)|'
    r"\x27(?:\\[\s\S]|[^\x27\\])*(?:\x27|\\?\Z))|[^\s,;}\]#]+)"
)
_ASSIGNMENT = re.compile(r"\b(" + _KEY + r'["\x27]?\s*[:=]\s*)' + _LITERAL, re.I)
_PRIVATE_BLOCK = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----[\s\S]*?"
    r"(?:-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----|\Z)"
)
_AUTHORIZATION = re.compile(
    r'\bAuthorization["\x27]?\s*[:=]\s*["\x27]?(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+',
    re.I,
)
_USERINFO = re.compile(r"\b([a-z][a-z0-9+.-]*://)[^/\s?#@]+@", re.I)
_TOKEN_PATTERNS = (
    re.compile(r"\bsk-[a-z0-9_.-]{15,}", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
)


def redact_credential_text(value):
    value = _PRIVATE_BLOCK.sub(MARKER, value)
    for pattern in _TOKEN_PATTERNS:
        value = pattern.sub(MARKER, value)
    value = _AUTHORIZATION.sub(MARKER, value)
    value = _USERINFO.sub(lambda match: match.group(1) + MARKER + "@", value)
    return _ASSIGNMENT.sub(lambda match: match.group(1) + '"' + MARKER + '"', value)


def redact_credential_values(value):
    if isinstance(value, str):
        return redact_credential_text(value)
    if isinstance(value, list):
        return [redact_credential_values(item) for item in value]
    if isinstance(value, dict):
        return {
            key: MARKER
            if isinstance(key, str) and _SENSITIVE_KEY.fullmatch(key)
            else redact_credential_values(item)
            for key, item in value.items()
        }
    return value
