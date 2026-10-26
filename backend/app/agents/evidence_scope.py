"""Qualify AI gap/suggestion wording against rule-layer evidence that was not sent."""
from __future__ import annotations

from app.agents.contracts import EvidenceAnalysis, RequirementEvidenceContext
from app.tools.display_path import display_file_path
from app.tools.matcher import MatchResult

_MISSING_CUES = ("未展示", "未提供", "缺少", "缺失", "没有", "请补充", "需补充", "补充")


def _key(entry) -> tuple[str, int, int]:
    return (entry.file_path, entry.line_start, entry.line_end)


def _short_material_ranges(entries) -> str:
    grouped: dict[str, list[tuple[int, int]]] = {}
    for entry in entries:
        grouped.setdefault(display_file_path(entry.file_path), []).append(
            (entry.line_start, entry.line_end)
        )
    return "；".join(
        f"{path} " + "、".join(f"第{start}–{end}行" for start, end in ranges)
        for path, ranges in grouped.items()
    )


def qualify_analysis(
    analysis: EvidenceAnalysis,
    result: MatchResult,
    sent_contexts: list[RequirementEvidenceContext],
) -> EvidenceAnalysis:
    """Replace absolute missing claims when a rule-layer evidence exists unsent.

    This only changes wording. It does not select evidence, change a score, or
    assert that the unsent material proves the missing fact.
    """
    rule_items = {str(item.requirement_id): item for item in result.items}
    sent = {
        str(context.requirement_id): {_key(entry) for entry in context.evidence}
        for context in sent_contexts
    }
    items = list(analysis.items)
    changed = False
    for index, item in enumerate(items):
        rule = rule_items.get(str(item.requirement_id))
        if rule is None:
            continue
        unsent = [
            entry for entry in rule.evidence_list
            if _key(entry) not in sent.get(str(item.requirement_id), set())
            and entry.snippet.strip()
        ]
        if not unsent:
            continue
        gap = item.information_gap or ""
        suggestion = item.suggestion or ""
        if not any(cue in gap or cue in suggestion for cue in _MISSING_CUES):
            continue
        materials = _short_material_ranges(unsent)
        items[index] = item.model_copy(update={
            "information_gap": (
                "规则层另有未发送材料："
                f"{materials}。材料中可能已包含，请先核对；仅对核对后仍未覆盖的场景再补充。"
            ),
            "suggestion": (
                "先核对规则层另有未发送材料："
                f"{materials}；材料中可能已包含，仅对核对后仍未覆盖的场景再补充。"
            ),
        })
        changed = True
    if not changed:
        return analysis
    return analysis.model_copy(update={"items": items})
