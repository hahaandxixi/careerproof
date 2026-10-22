"""Bounded lexical retrieval that supplements skill-specific static detectors.

This module deliberately does not call the hash-vector index a semantic model.
It ranks source-exact candidate lines with a small BM25-style scorer, then lets
the existing context expander and AI citation validator enforce the hard bounds.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import PurePosixPath

from app.tools.code_analyzer import CodeEvidence, ProjectFileSnapshot
from app.tools.evidence_selection import pytest_output_line

VERSION = "hybrid-lexical-v1"
MAX_CANDIDATES = 4
MAX_SCANNED_LINES = 20_000

_WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.+#-]*|[\u4e00-\u9fff]{2,}")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SAFE_SUFFIXES = {
    ".c",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".log",
    ".md",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
_IGNORED_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}
_STOP_TERMS = {
    "了解",
    "具有",
    "具备",
    "掌握",
    "熟悉",
    "能够",
    "相关",
    "使用",
    "实践",
    "经验",
    "开发",
    "实现",
    "and",
    "for",
    "the",
    "use",
    "with",
}


def lexical_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for raw in _WORD_PATTERN.findall(text):
        if re.fullmatch(r"[\u4e00-\u9fff]+", raw):
            if len(raw) <= 4:
                terms.add(raw)
            terms.update(raw[index : index + 2] for index in range(len(raw) - 1))
            continue
        normalized = raw.lower()
        terms.add(normalized)
        for part in re.split(r"[\s_.+#-]+", _CAMEL_BOUNDARY.sub(" ", raw)):
            if len(part) >= 2:
                terms.add(part.lower())
    return {term for term in terms if term not in _STOP_TERMS and len(term) >= 2}


def _eligible(file: ProjectFileSnapshot) -> bool:
    path = PurePosixPath(file.path.replace("\\", "/"))
    name = path.name.lower()
    return (
        path.suffix.lower() in _SAFE_SUFFIXES
        and name not in _IGNORED_NAMES
        and not name.endswith((".min.js", ".map"))
    )


def _comment_only(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith(("#", "//", "/*", "*", "<!--"))


def retrieve_requirement_candidates(
    requirement_title: str,
    skill: str,
    files: list[ProjectFileSnapshot],
    *,
    limit: int = MAX_CANDIDATES,
) -> list[CodeEvidence]:
    """Return low-strength, source-exact candidates without changing rule scores."""
    if limit < 1 or limit > MAX_CANDIDATES:
        raise ValueError(f"limit must be between 1 and {MAX_CANDIDATES}")
    skill_terms = lexical_terms(skill)
    query_terms = lexical_terms(f"{skill} {requirement_title}")
    is_pytest = skill.strip().lower() in {"pytest", "py.test"}
    if not query_terms:
        return []

    rows: list[tuple[ProjectFileSnapshot, int, str, set[str]]] = []
    output_lines: dict[str, int | None] = {}
    for file in files:
        if not _eligible(file):
            continue
        output_line = pytest_output_line(file.path, file.content) if is_pytest else None
        output_lines[file.path] = output_line
        for line_number, line in enumerate(file.content.splitlines(), 1):
            if len(rows) >= MAX_SCANNED_LINES:
                break
            if _comment_only(line):
                continue
            terms = lexical_terms(f"{file.path} {line}")
            overlap = query_terms & terms
            # A skill-name hit is sufficient; otherwise require two query terms
            # so generic words do not become evidence candidates.
            if not (skill_terms & terms) and len(overlap) < 2 and line_number != output_line:
                continue
            rows.append((file, line_number, line, terms))
        if len(rows) >= MAX_SCANNED_LINES:
            break
    if not rows:
        return []

    document_frequency = Counter(
        term for term in query_terms for row in rows if term in row[3]
    )
    row_count = len(rows)

    def score(row: tuple[ProjectFileSnapshot, int, str, set[str]]) -> tuple[bool, float, int, str]:
        file, line_number, line, terms = row
        overlap = query_terms & terms
        idf_score = sum(
            math.log(1 + (row_count + 1) / (document_frequency[term] + 1))
            for term in overlap
        )
        exact_skill = (
            2.5
            if skill.strip() and skill.strip().lower() in f"{file.path} {line}".lower()
            else 0.0
        )
        code_signal = (
            0.4
            if re.search(r"[(){}=]|\b(?:class|def|function|select|insert)\b", line, re.I)
            else 0.0
        )
        output_summary = line_number == output_lines.get(file.path)
        return output_summary, idf_score + exact_skill + code_signal, -line_number, file.path

    ranked = sorted(rows, key=score, reverse=True)
    selected: list[CodeEvidence] = []
    seen_files: Counter[str] = Counter()
    for file, line_number, line, _ in ranked:
        normalized_path = file.path.replace("\\", "/")
        if seen_files[normalized_path] >= 2:
            continue
        seen_files[normalized_path] += 1
        selected.append(
            CodeEvidence(
                skill=skill,
                evidence_type="retrieved_context",
                file_path=normalized_path,
                line_start=line_number,
                line_end=line_number,
                snippet=line.strip()[:240],
                strength="low",
                explanation=(
                    "混合检索发现与岗位要求词项相关的原文；仅作为AI核对候选，"
                    "不直接证明功能完成、运行结果或本人贡献。"
                ),
                content_hash=hashlib.sha256(file.content.encode("utf-8")).hexdigest(),
            )
        )
        if len(selected) >= limit:
            break
    return selected
