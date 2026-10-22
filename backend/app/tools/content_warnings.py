"""Bounded local phrase hints; findings are not violations or upload decisions.

Only explicit phrases or same-sentence combinations are checked. Quoted examples,
filtering tests and legitimate discussion can also match and require human context.
No source excerpts are returned. Reaching the finding cap stops the scan and marks
it incomplete, even when that hit happens to be the final available match.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypedDict

MAX_FILES = 200
MAX_CHARACTERS = 500_000
MAX_FINDINGS = 30
MAX_PATH_CHARACTERS = 1_024

CATEGORIES = ("sexual_solicitation", "abuse_threat", "recruitment_fraud", "spam")
_SENTENCE_END = re.compile(r"[。！？!?；;]+")


class ContentWarning(TypedDict):
    category: str
    ruleId: str
    path: str
    line: int


class ContentWarningReport(TypedDict):
    version: str
    warningOnly: bool
    findings: list[ContentWarning]
    counts: dict[str, int]
    truncated: bool
    truncationReasons: list[str]
    scannedFiles: int
    scannedCharacters: int
    limits: dict[str, int]


@dataclass(frozen=True)
class _Rule:
    category: str
    rule_id: str
    groups: tuple[tuple[str, ...], ...]

    def matches(self, sentence: str) -> bool:
        return all(any(phrase in sentence for phrase in group) for group in self.groups)


_RULES = (
    _Rule(
        "sexual_solicitation",
        "sexual.contact_solicitation",
        (("裸聊", "约炮", "色情陪聊"), ("微信", "加v", "加 v", "vx", "私聊", "联系", "qq")),
    ),
    _Rule(
        "abuse_threat",
        "abuse.targeted_threat",
        (("我要杀了你", "我要弄死你", "i will kill you", "i am going to kill you"),),
    ),
    _Rule(
        "abuse_threat",
        "abuse.targeted_insult",
        (("你这个废物", "你个废物"),),
    ),
    _Rule(
        "recruitment_fraud",
        "recruitment.upfront_fee",
        (
            ("入职", "面试", "录用", "应聘", "招聘"),
            (
                "先交押金",
                "先缴押金",
                "缴纳押金",
                "先交保证金",
                "缴纳保证金",
                "先交培训费",
                "缴纳培训费",
                "交钱才能",
            ),
        ),
    ),
    _Rule(
        "recruitment_fraud",
        "recruitment.order_rebate",
        (("刷单",), ("返佣", "返利", "日结", "兼职")),
    ),
    _Rule(
        "spam",
        "spam.guaranteed_income_contact",
        (
            ("稳赚不赔", "日赚千元", "躺赚", "guaranteed profit"),
            ("加微信", "私聊", "扫码", "联系我", "contact me"),
        ),
    ),
)


def _checked_limit(value: int, maximum: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def scan_content_warnings(
    sources: Iterable[tuple[str, str]],
    *,
    max_files: int = MAX_FILES,
    max_characters: int = MAX_CHARACTERS,
    max_findings: int = MAX_FINDINGS,
) -> ContentWarningReport:
    """Inspect ``(path, text)`` pairs without file I/O, external calls or mutation.

    Counts are observed unique source/line/rule hits, not occurrences of a word.
    Line numbers refer to original LF-delimited input (including CRLF files).
    Limits may be lowered but never exceed the module's hard ceilings. Characters
    count original Unicode code points, including line endings, before NFKC folding.
    """
    max_files = _checked_limit(max_files, MAX_FILES, "max_files")
    max_characters = _checked_limit(max_characters, MAX_CHARACTERS, "max_characters")
    max_findings = _checked_limit(max_findings, MAX_FINDINGS, "max_findings")
    report: ContentWarningReport = {
        "version": "local-content-warnings-v1",
        "warningOnly": True,
        "findings": [],
        "counts": dict.fromkeys(CATEGORIES, 0),
        "truncated": False,
        "truncationReasons": [],
        "scannedFiles": 0,
        "scannedCharacters": 0,
        "limits": {
            "maxFiles": max_files,
            "maxCharacters": max_characters,
            "maxFindings": max_findings,
            "maxPathCharacters": MAX_PATH_CHARACTERS,
        },
    }

    def mark_incomplete(reason: str) -> None:
        report["truncated"] = True
        if reason not in report["truncationReasons"]:
            report["truncationReasons"].append(reason)

    for source_index, (path, text) in enumerate(sources):
        if source_index >= max_files:
            mark_incomplete("file_limit")
            break
        if not isinstance(path, str) or not isinstance(text, str):
            raise TypeError("sources must contain (path, text) string pairs")
        if len(path) > MAX_PATH_CHARACTERS:
            mark_incomplete("path_length_limit")
            continue
        remaining = max_characters - report["scannedCharacters"]
        if remaining == 0 and text:
            mark_incomplete("character_limit")
            break
        report["scannedFiles"] += 1
        scan_end = min(len(text), remaining)
        offset = 0
        line_number = 1
        while offset < scan_end:
            newline = text.find("\n", offset, scan_end)
            line_end = scan_end if newline == -1 else newline
            raw_line = text[offset:line_end]
            consumed = line_end - offset + (newline != -1)
            report["scannedCharacters"] += consumed
            normalized = unicodedata.normalize("NFKC", raw_line).casefold()
            sentences = _SENTENCE_END.split(normalized)
            for rule in _RULES:
                if not any(rule.matches(sentence) for sentence in sentences):
                    continue
                report["findings"].append(
                    {
                        "category": rule.category,
                        "ruleId": rule.rule_id,
                        "path": path,
                        "line": line_number,
                    }
                )
                report["counts"][rule.category] += 1
                if len(report["findings"]) == max_findings:
                    mark_incomplete("finding_limit")
                    return report
            offset = line_end + (newline != -1)
            line_number += 1
        if scan_end < len(text):
            mark_incomplete("character_limit")
            break
    return report
