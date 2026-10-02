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


def file_coverage(evidence) -> list[dict]:
    groups = {}
    for entry in evidence:
        if entry.provenance == "portfolio":
            groups.setdefault(entry.file_path, []).append(entry)
    result = []
    for path, entries in sorted(groups.items()):
        counts = {entry.source_line_count for entry in entries}
        if len(counts) != 1 or None in counts:
            continue
        count = counts.pop()
        if not all(1 <= entry.line_start <= entry.line_end <= count for entry in entries):
            continue
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
        result.append(
            {
                "file_path": path,
                "source_line_count": count,
                "covered_line_count": covered,
                "fully_covered": covered == count,
                "citation_ids": list(dict.fromkeys(entry.citation_id for entry in entries)),
            }
        )
    return result


_SOURCE_REQUEST = re.compile(
    r"(?:提交|补充|提供|上传|补交)"
    r"(?P<subject>(?:该|当前|此|本|对应|这段)?(?:函数的?|文件的?)?)"
    r"完整(?P<source>函数(?:原文|源码|上下文)|文件|源码|原文|上下文)"
)
_EXPLICIT_REPEAT_REQUEST = re.compile(
    r"(?:再次|重新|重复)(?:提交|补充|提供|上传|补交)"
    r"(?:该|当前|此|本|对应|这段)(?P<kind>函数|文件)(?:的)?"
    r"(?:完整)?(?:实现代码|源码|代码|原文|函数体|文件内容)"
)
_NEW_MATERIAL_SUFFIX = re.compile(
    r"(?:的)?(?:运行|执行|测试|验证|提交|贡献|历史|新版本|修订|修正|更新|修改|补全|新增)"
)
_INTERNAL_REASON = re.compile(
    r"rating_ceiling|function_source_coverage|context_complete|provenance"
    r"|受(?:到)?(?:程序|规则|评级)?上限限制|因(?:程序|规则|评级)?上限(?:限制|约束)"
)


def redundant_source_request(text: str, evidence) -> bool:
    personal = [entry for entry in evidence if entry.provenance == "portfolio"]
    coverage = file_coverage(personal)
    files_complete = bool(personal) and len(coverage) == len({e.file_path for e in personal})
    files_complete = files_complete and all(row["fully_covered"] for row in coverage)
    functions_complete = all_cited_functions_covered(evidence)
    for match in _EXPLICIT_REPEAT_REQUEST.finditer(text):
        if _NEW_MATERIAL_SUFFIX.match(text[match.end() :]):
            continue
        if match["kind"] == "函数" and functions_complete:
            return True
        if match["kind"] == "文件" and files_complete:
            return True
    for match in _SOURCE_REQUEST.finditer(text):
        # Runtime records and contribution history are new evidence, even when
        # the source file was fully shown. Only reject repeated source requests.
        if _NEW_MATERIAL_SUFFIX.match(text[match.end() :]):
            continue
        subject, source = match["subject"], match["source"]
        if source == "文件" and subject and files_complete:
            return True
        if (
            source != "文件"
            and ("函数" in subject or source.startswith("函数"))
            and functions_complete
        ):
            return True
        if "文件" in subject and files_complete:
            return True
    return False


def task_plan_redundant_source_request(plan, evidence) -> bool:
    """Apply the saved-plan source guard to every human-readable plan field.

    Task plans are persisted with reports and can outlive the validator version
    that created them.  Rechecking the deliverable, steps, and acceptance
    criteria at read time prevents an old plan from quietly reintroducing a
    request for source that is already fully visible.
    """
    if not isinstance(plan, dict):
        return False
    texts: list[str] = []
    for key in ("deliverable", "steps", "acceptanceChecks", "acceptance_checks"):
        value = plan.get(key)
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, list):
            texts.extend(text for text in value if isinstance(text, str))
    return any(redundant_source_request(text, evidence) for text in texts)


def internal_rating_reason(text: str) -> bool:
    return bool(_INTERNAL_REASON.search(text))
