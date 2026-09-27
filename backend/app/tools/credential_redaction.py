"""Bounded credential-shape filtering for external text context and authorized MCP exports.

This is not a universal secret detector. Encoded/unknown formats and unlabeled
fragments may not be recognized; source records and hashes remain unchanged.
"""

import re
import tokenize
from io import StringIO

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


def _python_credential_ranges(value):
    # Tokenize partial snippets without executing or importing uploaded code.
    tokens = []
    try:
        for token in tokenize.generate_tokens(StringIO(value).readline):
            tokens.append(token)
    except (tokenize.TokenError, IndentationError):
        pass
    offsets = [0]
    for line in value.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))

    def offset(position):
        return offsets[min(position[0] - 1, len(offsets) - 1)] + position[1]

    annotations, defaults = set(), []
    for index, token in enumerate(tokens[:-1]):
        if token.type != tokenize.NAME or not _SENSITIVE_KEY.fullmatch(token.string):
            continue
        following = tokens[index + 1]
        if following.type != tokenize.OP or following.string not in {":", "="}:
            continue
        annotated = following.string == ":"
        if annotated:
            annotations.add(offset(token.start))
        depth = 0
        for position in range(index + 2 if annotated else index + 1, len(tokens)):
            current = tokens[position]
            if depth == 0 and (
                current.type in {tokenize.NEWLINE, tokenize.ENDMARKER, tokenize.COMMENT}
                or current.string in {",", ")", ";"}
            ):
                break
            if current.type == tokenize.OP and current.string == "=" and depth == 0:
                start = offset(current.end)
                depth = 0
                end = len(value)
                for default in tokens[position + 1 :]:
                    if depth == 0 and (
                        default.type in {tokenize.NEWLINE, tokenize.ENDMARKER, tokenize.COMMENT}
                        or default.string in {",", ")", ";"}
                    ):
                        end = offset(default.start)
                        break
                    if default.type == tokenize.OP:
                        if default.string in {"(", "[", "{"}:
                            depth += 1
                        elif default.string in {")", "]", "}"}:
                            depth -= 1
                if value[start:end].strip():
                    defaults.append((start, end))
                break
            if current.type == tokenize.OP:
                if current.string in {"(", "[", "{"}:
                    depth += 1
                elif current.string in {")", "]", "}"}:
                    depth -= 1
    merged = []
    for start, end in sorted(defaults):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return annotations, merged


def redact_credential_text(value, *, python_source=False):
    if python_source:
        _, defaults = _python_credential_ranges(value)
        for start, end in sorted(set(defaults), reverse=True):
            # Preserve line count for source locators, including multiline defaults.
            lines = "\n" * value[start:end].count("\n")
            value = value[:start] + ' "' + MARKER + '"' + lines + value[end:]
    value = _PRIVATE_BLOCK.sub(MARKER, value)
    for pattern in _TOKEN_PATTERNS:
        value = pattern.sub(MARKER, value)
    value = _AUTHORIZATION.sub(MARKER, value)
    value = _USERINFO.sub(lambda match: match.group(1) + MARKER + "@", value)
    annotations = _python_credential_ranges(value)[0] if python_source else set()
    return _ASSIGNMENT.sub(
        lambda match: match.group(0)
        if match.start() in annotations
        else match.group(1) + '"' + MARKER + '"',
        value,
    )


def redact_credential_values(value):
    if isinstance(value, str):
        return redact_credential_text(value)
    if isinstance(value, list):
        return [redact_credential_values(item) for item in value]
    if isinstance(value, dict):
        path = value.get("file_path", value.get("filePath", ""))
        return {
            key: MARKER
            if isinstance(key, str) and _SENSITIVE_KEY.fullmatch(key)
            else redact_credential_text(item, python_source=True)
            if key == "snippet"
            and isinstance(item, str)
            and isinstance(path, str)
            and path.endswith(".py")
            else redact_credential_values(item)
            for key, item in value.items()
        }
    return value
