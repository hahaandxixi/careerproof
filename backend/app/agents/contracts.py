from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceCandidate(StrictModel):
    citation_id: str = Field(pattern=r"^R\d+-E\d+$")
    file_path: str = Field(min_length=1, max_length=1000)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    evidence_type: str = Field(min_length=1, max_length=100)
    strength: str = Field(min_length=1, max_length=20)
    snippet: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(
        min_length=1, max_length=4000
    )
    context_complete: bool = False
    context_note: str = "局部证据；运行结果和本人贡献仍需核验"
    provenance: Literal["portfolio", "reference"] = "portfolio"


class RequirementEvidenceContext(StrictModel):
    requirement_id: str = Field(min_length=1, max_length=100)
    requirement_title: str = Field(min_length=1, max_length=2000)
    skill: str = Field(min_length=1, max_length=100)
    verdict: str = Field(min_length=1, max_length=30)
    rule_score: float = Field(ge=0, le=1)
    claimed: bool
    claim_text: str | None = Field(default=None, max_length=500)
    evidence: list[EvidenceCandidate] = Field(default_factory=list, max_length=3)
    rating_rubric: dict = Field(default_factory=dict)
    rating_ceiling: int | None = Field(default=None, ge=1, le=3)


class RetrievalToolCall(StrictModel):
    requirement_id: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=2, max_length=200)


class CriterionDecision(StrictModel):
    criterion: Literal["relevance", "operation", "task"]
    supported: bool
    citation_ids: list[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(min_length=1, max_length=300)


class AIRating(StrictModel):
    level: int | None = Field(default=None, ge=1, le=3)
    reason: str = Field(min_length=1, max_length=500)
    criteria: list[CriterionDecision] = Field(min_length=3, max_length=3)


class AIRequirementAnalysis(StrictModel):
    requirement_id: str = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=1, max_length=1000)
    citation_ids: list[str] = Field(default_factory=list, max_length=3)
    information_gap: str | None = Field(default=None, max_length=500)
    suggestion: str | None = Field(default=None, max_length=500)
    confidence: float = Field(ge=0, le=1)
    rating: AIRating | None = None


class ModelUsage(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_hit_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)


class EvidenceAnalysis(StrictModel):
    summary: str = Field(min_length=1, max_length=2000)
    items: list[AIRequirementAnalysis] = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    usage: ModelUsage = Field(default_factory=ModelUsage)


def overclaim_flags(text: str) -> list[str]:
    """Conservative lexical guard, NOT a semantic entailment metric."""
    # This exact rubric phrase describes relevance, not job fitness or ability.
    # Keep "满足岗位要求" and all other broad fitness claims subject to the guard.
    for source, replacement in (
        ("不满足相关性要求", "缺少相关线索"),
        ("满足相关性要求", "存在相关线索"),
        ("不满足实质操作要求", "缺少实质操作证据"),
        ("满足实质操作要求", "存在实质操作证据"),
        ("不满足完整任务要求", "缺少完整任务证据"),
        ("满足完整任务要求", "存在完整任务证据"),
    ):
        text = text.replace(source, replacement)
    text = re.sub(
        r"(?:声称|声明|自述).{0,40}(?:测试|用例|代码|服务).{0,12}"
        r"(?:全部通过|已通过|运行成功).{0,50}"
        r"(?:不作为事实|不予采纳|不采纳|未核验|待核验)",
        "已明确拒绝采纳的材料声明",
        text,
    )
    patterns = {
        "ability_claim": r"(?:证明|表明|确认|可见).{0,12}(?:具备|拥有|掌握).{0,30}(?:能力|技能)|"
        r"(?:具备|拥有).{0,24}能力|熟练掌握|精通|胜任|满足.{0,25}(?:岗位|要求)",
        "negative_ability": r"不具备.{0,20}能力|没有.{0,20}能力|能力不足",
        "authorship_claim": r"(?:候选人|本人|作者).{0,6}(?:编写了|完成了|实现了|开发了)",
        "execution_claim": r"(?:测试|用例|代码|服务).{0,12}(?:全部通过|已通过|运行成功)|"
        r"(?:已验证|已经验证).{0,16}(?:可用|性能|正确)|"
        r"(?:proves?|demonstrates?).{0,30}(?:ability|competenc)|tests? passed",
    }
    flags = set()
    for sentence in re.split(r"[。！？；，,\n]", text):
        for label, pattern in patterns.items():
            for match in re.finditer(pattern, sentence, re.I):
                prefix = sentence[max(0, match.start() - 16) : match.start()]
                uncertain = re.search(r"是否", match.group()) or re.search(
                    r"不能|无法|不代表|不等于|不足以|未能|尚不能|未验证|尚未核实|待核验|需核验",
                    prefix,
                )
                # A scoped attribution reports the claim; it does not endorse it.
                attributed = (
                    re.fullmatch(r"材料中仅包含对.+的声明", sentence.strip())
                    or re.fullmatch(r"声明中提到.+", sentence.strip())
                ) and not re.search(r"证实|确认|验证|确实|事实|证明", sentence)
                explicitly_rejected_claim = bool(
                    re.search(r"声称|声明|自述", prefix)
                    and re.search(
                        r"不作为事实|不予采纳|不采纳|未核验|待核验",
                        sentence[match.end() :],
                    )
                )
                if not uncertain and not attributed and not explicitly_rejected_claim:
                    flags.add(label)
    return sorted(flags)


def validate_grounded_analysis(
    contexts: list[RequirementEvidenceContext], analysis: EvidenceAnalysis
) -> None:
    if overclaim_flags(analysis.summary):
        raise ValueError("AI summary contains an unsupported ability or execution claim")
    expected_ids = [context.requirement_id for context in contexts]
    actual_ids = [item.requirement_id for item in analysis.items]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("AI analysis contains duplicate requirement IDs")
    if set(actual_ids) != set(expected_ids):
        raise ValueError("AI analysis requirement IDs do not match the request")

    context_by_id = {context.requirement_id: context for context in contexts}
    for item in analysis.items:
        context = context_by_id[item.requirement_id]
        allowed = {evidence.citation_id for evidence in context.evidence}
        if len(item.citation_ids) != len(set(item.citation_ids)):
            raise ValueError("AI analysis contains duplicate citations")
        if not set(item.citation_ids).issubset(allowed):
            raise ValueError("AI analysis contains an unknown or cross-requirement citation")
        personal_citations = {
            evidence.citation_id
            for evidence in context.evidence
            if evidence.provenance == "portfolio"
        }
        if context.evidence and context.verdict in {"supported", "partial"}:
            if not personal_citations.intersection(item.citation_ids):
                raise ValueError("AI analysis omitted citations for an evidenced requirement")
        elif personal_citations.intersection(item.citation_ids):
            raise ValueError("AI analysis cited personal evidence for an unevidenced requirement")
        if context.verdict in {"partial", "claimed_only", "gap", "unsupported"} or any(
            not evidence.context_complete for evidence in context.evidence
        ):
            if not item.information_gap:
                raise ValueError("AI analysis omitted the information gap")
            if not item.suggestion:
                raise ValueError("AI analysis omitted the evidence suggestion")
        combined = " ".join(
            value for value in (item.explanation, item.information_gap, item.suggestion) if value
        )
        if overclaim_flags(combined):
            raise ValueError("AI analysis contains an unsupported ability or execution claim")
        cited_evidence = [
            evidence for evidence in context.evidence if evidence.citation_id in item.citation_ids
        ]
        if (
            item.information_gap
            and any(evidence.context_complete for evidence in cited_evidence)
            and re.search(
                r"(?:未核验|无法确认|不能确认|不清楚).{0,10}函数体(?:是否|有无|有没有|包含)",
                item.information_gap,
            )
        ):
            raise ValueError("AI information gap contradicts the complete function context")
        if context.verdict == "unsupported":
            boundary_markers = ("规则", "暂不支持", "无法评估", "不能判断", "无法判断")
            if not any(marker in combined for marker in boundary_markers):
                raise ValueError("AI analysis obscured the unsupported-evaluator boundary")
            if any(phrase in combined for phrase in ("无关", "移除", "删除")):
                raise ValueError("AI analysis contradicted an explicit job requirement")
        if context.rating_rubric:
            if item.rating is None:
                raise ValueError("AI omitted the rubric rating")
            rating = item.rating
            decisions = {d.criterion: d for d in rating.criteria}
            if set(decisions) != {"relevance", "operation", "task"}:
                raise ValueError("AI rating criteria must be complete and unique")
            if (
                context.skill == "FastAPI"
                and "测试" in context.requirement_title
                and decisions["task"].supported
            ):
                task_sources = [
                    evidence.snippet
                    for evidence in context.evidence
                    if evidence.citation_id in decisions["task"].citation_ids
                    and evidence.provenance == "portfolio"
                ]
                if not any(
                    re.search(r"(?m)^\s*assert\b|\bpytest\.raises\b|\bself\.assert\w*\b", source)
                    for source in task_sources
                ):
                    raise ValueError("AI FastAPI task rating lacks cited test assertions")
            for decision in rating.criteria:
                if len(decision.citation_ids) != len(set(decision.citation_ids)):
                    raise ValueError("AI rating contains duplicate citations")
                if not set(decision.citation_ids).issubset(set(item.citation_ids)):
                    raise ValueError("AI rating cites evidence outside the item citations")
                if decision.supported and not decision.citation_ids:
                    raise ValueError("AI rating criterion has no supporting citation")
                if decision.supported:
                    from app.tools.evidence_levels import _rule_classification

                    cited = [
                        e.model_dump()
                        for e in context.evidence
                        if e.citation_id in decision.citation_ids
                    ]
                    cap = _rule_classification(
                        {"skill": context.skill, "evidenceList": cited}, context.verdict
                    )["evidence_level"]
                    required = {"relevance": 1, "operation": 2, "task": 3}[decision.criterion]
                    if cap is None or cap < required:
                        raise ValueError("AI criterion citations cannot support this evidence tier")
                if overclaim_flags(decision.reason):
                    raise ValueError("AI rating criterion overclaims")
            flags = [decisions[key].supported for key in ("relevance", "operation", "task")]
            if (flags[1] and not flags[0]) or (flags[2] and not flags[1]):
                raise ValueError("AI rating prerequisites are inconsistent")
            derived = sum(flags) or None
            if rating.level != derived:
                raise ValueError("AI rating level disagrees with criterion decisions")
            if rating.level is not None and (
                context.rating_ceiling is None or rating.level > context.rating_ceiling
            ):
                raise ValueError("AI rating exceeds evidence ceiling")
            if overclaim_flags(rating.reason):
                raise ValueError("AI rating reason overclaims")
