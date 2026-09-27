"""Query-directed, bounded lookup over verified task-local text snapshots only."""

from __future__ import annotations

import ast
import hashlib

from app.tools.code_analyzer import CodeEvidence
from app.tools.evidence_context import retrieve_context
from app.tools.hybrid_retrieval import _comment_only, _eligible, lexical_terms

VERSION = "frozen-directed-v1"
MAX_SCANNED_LINES = 20_000
MAX_ANCHORS = 16
_FORBIDDEN_TERMS = {
    "password",
    "secret",
    "secrets",
    "credential",
    "credentials",
    "api_key",
    "apikey",
    "email",
    "phone",
    "密码",
    "密钥",
    "凭据",
    "身份证",
    "手机号",
    "邮箱",
}
_GENERIC_TERMS = {"return", "def", "function", "class", "if", "else", "try", "except"}


def search_frozen_sources(sources, query: str, skill: str, shown):
    """No filesystem, network, code execution, or model calls occur here."""
    terms = lexical_terms(query)
    if terms & _FORBIDDEN_TERMS or any(word in query for word in ("身份证", "手机号", "邮箱")):
        raise ValueError("Directed retrieval cannot search credentials or identifiers")
    terms -= _GENERIC_TERMS
    covered = {}
    for entry in shown:
        covered.setdefault(entry.file_path, set()).update(
            range(entry.line_start, entry.line_end + 1)
        )
    rows = []
    scanned = 0
    exhausted = False
    for source in sources:
        file = source.file
        if not _eligible(file):
            continue
        if hashlib.sha256(file.content.encode("utf-8")).hexdigest() != source.content_hash:
            raise ValueError("Frozen retrieval source hash mismatch")
        for number, line in enumerate(file.content.splitlines(), 1):
            if scanned >= MAX_SCANNED_LINES:
                exhausted = True
                break
            scanned += 1
            if number in covered.get(file.path, set()) or _comment_only(line):
                continue
            overlap = terms & lexical_terms(line)
            if overlap:
                rows.append((len(overlap), file.path, number, line, source))
        if exhausted:
            break
    rows.sort(key=lambda row: (-row[0], row[1], row[2]))
    candidates = []
    seen = set()
    trees = {}
    for _, _, number, line, source in rows[:MAX_ANCHORS]:
        file = source.file
        if file.path not in trees:
            try:
                trees[file.path] = ast.parse(file.content) if file.path.endswith(".py") else None
            except (SyntaxError, ValueError):
                trees[file.path] = None
        anchor = CodeEvidence(
            skill=skill,
            evidence_type="retrieved_context",
            file_path=file.path,
            line_start=number,
            line_end=number,
            snippet=line.strip()[:240],
            strength="low",
            explanation="按本轮查询从冻结材料补取的原文，仅作核对候选，不直接证明能力或运行结果。",
            content_hash=source.content_hash,
        )
        try:
            candidate = retrieve_context(anchor, file, trees[file.path])
        except ValueError:
            continue
        key = (candidate.file_path, candidate.line_start, candidate.line_end)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) == 4:
            break
    return candidates, {
        "engine": VERSION,
        "scannedLines": scanned,
        "scanLimit": MAX_SCANNED_LINES,
        "scanLimitReached": exhausted,
        "candidateCount": len(candidates),
        "maxAnchors": MAX_ANCHORS,
        "sourceExact": True,
    }


def can_search_frozen_sources(sources, shown) -> bool:
    if not sources or len(shown) >= 3:
        return False
    covered = {}
    for entry in shown:
        covered.setdefault(entry.file_path, set()).update(
            range(entry.line_start, entry.line_end + 1)
        )
    scanned = 0
    for source in sources:
        if not _eligible(source.file):
            continue
        for number, line in enumerate(source.file.content.splitlines(), 1):
            if scanned >= MAX_SCANNED_LINES:
                return False
            scanned += 1
            if number not in covered.get(source.file.path, set()) and not _comment_only(line):
                return True
    return False
