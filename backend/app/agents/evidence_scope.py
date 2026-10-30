"""Keep concrete model gaps intact; reject claims beyond the supplied scope."""
from __future__ import annotations

import re

from app.agents.contracts import EvidenceAnalysis, RequirementEvidenceContext
from app.tools.matcher import MatchResult

_PROJECT_ABSENCE = re.compile(
    r"(?:整个项目|全部材料|代码库).{0,12}(?:没有|未提供|未包含|不存在|缺少)"
    r"|(?:项目|材料)(?:中)?(?:完全|根本)?(?:没有|未包含|未提供|不存在).{0,8}"
    r"(?:测试代码|测试实现|测试(?!运行|执行|记录|结果)|路由|接口实现|业务实现|源码)"
)


def _key(entry) -> tuple[str, int, int]:
    return (entry.file_path, entry.line_start, entry.line_end)


def qualify_analysis(
    analysis: EvidenceAnalysis,
    result: MatchResult,
    sent_contexts: list[RequirementEvidenceContext],
) -> EvidenceAnalysis:
    """Unsent sources are a separate scope fact, never a replacement diagnosis.

    The report retains all rule sources and the sent-source identities, allowing
    readers to locate omitted material without inventing a new model conclusion.
    """
    rule_items = {str(item.requirement_id): item for item in result.items}
    sent = {
        str(context.requirement_id): {_key(entry) for entry in context.evidence}
        for context in sent_contexts
    }
    for item in analysis.items:
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
        text = " ".join(v for v in (item.explanation, item.information_gap, item.suggestion) if v)
        if _PROJECT_ABSENCE.search(text):
            raise ValueError("AI absence claim exceeds the supplied evidence scope; additional rule sources were not sent")
    return analysis
