"""Union source ranges for known Python function bounds, without rating changes."""

from __future__ import annotations

import re


def function_coverage(evidence) -> list[dict]:
    groups = {}
    for entry in evidence:
        start, end = entry.function_line_start, entry.function_line_end
        if (
            entry.provenance != "portfolio"
            or start is None
            or end is None
            or not start <= entry.line_start <= entry.line_end <= end
        ):
            continue
        groups.setdefault((entry.file_path, start, end), []).append(entry)
    results = []
    for (path, start, end), entries in sorted(groups.items()):
        intervals = sorted((entry.line_start, entry.line_end) for entry in entries)
        covered = 0
        left, right = intervals[0]
        for next_left, next_right in intervals[1:]:
            if next_left <= right + 1:
                right = max(right, next_right)
            else:
                covered += right - left + 1
                left, right = next_left, next_right
        covered += right - left + 1
        results.append(
            {
                "file_path": path,
                "function_line_start": start,
                "function_line_end": end,
                "covered_line_count": covered,
                "fully_covered": covered == end - start + 1,
                "citation_ids": list(dict.fromkeys(entry.citation_id for entry in entries)),
            }
        )
    return results


_FUNCTION_CONTEXT = re.compile(
    r"^(?:(?:当前|该|此|本|这段)的?)?函数(?:体)?(?:的)?(?:完整)?(?:上下文|源码)"
)
_NEGATIVE = re.compile(r"未展示|未提供|未给出|缺少|缺失|无法确认|无法核实|补充")
_POSITIVE = re.compile(r"已(?:展示|提供|给出|覆盖)|完整提供")


def missing_function_context_claim(text: str) -> bool:
    """Narrow lexical consistency check, not general semantic entailment."""
    for clause in re.split(r"[。！？;；，,\n]", text):
        negative = _NEGATIVE.search(clause)
        if negative and not re.search(
            r"(?:旧报告|上次|历史记录|不应|不能|不要|声称).{0,8}$", clause[: negative.start()]
        ):
            for part in clause[negative.end() :].split("、"):
                match = _FUNCTION_CONTEXT.match(part.strip())
                if match and not _POSITIVE.search(part):
                    # External behaviour remains unknown even when source is covered.
                    remainder = part.strip()[match.end() :]
                    if not re.search(r"运行|贡献|依赖|调用", remainder):
                        return True
        if _FUNCTION_CONTEXT.match(clause.strip()) and re.search(
            r"不完整|尚未(?:展示|提供)|(?:仍|有)缺口", clause
        ):
            return True
    return False


def all_cited_functions_covered(evidence) -> bool:
    personal = [entry for entry in evidence if entry.provenance == "portfolio"]
    if not personal or any(entry.function_line_start is None for entry in personal):
        return False
    coverage = function_coverage(personal)
    return bool(coverage) and all(entry["fully_covered"] for entry in coverage)
