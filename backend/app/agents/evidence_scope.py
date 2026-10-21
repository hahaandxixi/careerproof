"""Qualify AI gap/suggestion wording against rule-layer evidence that was not sent."""
from __future__ import annotations

from app.agents.contracts import EvidenceAnalysis, RequirementEvidenceContext
from app.tools.matcher import MatchResult

_MISSING_CUES = ("未展示", "未提供", "缺少", "缺失", "没有", "请补充", "需补充", "补充")


def _key(entry) -> tuple[str, int, int]:
    return (entry.file_path, entry.line_start, entry.line_end)


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
        files = "、".join(
            f"{entry.file_path}:{entry.line_start}-{entry.line_end}" for entry in unsent[:3]
        )
        items[index] = item.model_copy(update={
            "information_gap": (
                "本次片段未覆盖模型判断所需的部分材料；规则层保存了未发送证据："
                f"{files}。材料中可能已包含，请先核对这些材料后再判断是否仍需补充。"
            ),
            "suggestion": (
                "先核对规则层保存但未发送的材料（"
                f"{files}）；材料中可能已包含，仅对核对后仍未覆盖的场景再补充具体材料。"
            ),
        })
        changed = True
    if not changed:
        return analysis
    return analysis.model_copy(update={"items": items})
