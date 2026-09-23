from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

from app.tools.code_analyzer import (
    CodeEvidence,
    ProjectFileSnapshot,
    canonical_skill,
    find_evidence,
)
from app.tools.hybrid_retrieval import VERSION as HYBRID_RETRIEVAL_VERSION
from app.tools.hybrid_retrieval import retrieve_requirement_candidates
from app.tools.resume_parser import SkillClaim

STRENGTH_SCORE = {"high": 0.65, "medium": 0.4, "low": 0.15}
FORMULA_VERSION = "evidence-v3"


@dataclass(frozen=True, slots=True)
class RequirementInput:
    id: UUID
    title: str
    skill: str
    weight: int


@dataclass(frozen=True, slots=True)
class MatchItemResult:
    requirement_id: UUID
    requirement_title: str
    skill: str
    claimed: bool
    claim_text: str | None
    evidence: CodeEvidence | None
    evidence_list: list[CodeEvidence]
    verdict: str
    ai_confidence: float | None
    rule_base_score: float
    weight: int
    final_score: float | None
    explanation: str
    formula_version: str


@dataclass(frozen=True, slots=True)
class MatchResult:
    overall_score: float | None
    items: list[MatchItemResult]
    gaps: list[str]
    claimed_only: list[str]
    summary: str
    retrieval_steps: list[dict] = field(default_factory=list)
    grounding_error: bool = False


def match_candidate(
    requirements: list[RequirementInput],
    claims: list[SkillClaim],
    files: list[ProjectFileSnapshot],
    *,
    semantic_candidates: dict[UUID, list[CodeEvidence]] | None = None,
) -> MatchResult:
    claims_by_skill = {canonical_skill(claim.skill): claim for claim in claims}
    items: list[MatchItemResult] = []
    weighted_total = 0.0
    total_weight = 0
    retrieved_count = 0

    for requirement in requirements:
        skill = canonical_skill(requirement.skill)
        claim = claims_by_skill.get(skill) if skill else None
        detected_evidence = find_evidence(files, requirement.skill)
        detected_keys = {
            (evidence.file_path, evidence.line_start, evidence.line_end)
            for evidence in detected_evidence
        }
        semantic_evidence = [
            evidence
            for evidence in (semantic_candidates or {}).get(requirement.id, [])
            if (evidence.file_path, evidence.line_start, evidence.line_end) not in detected_keys
        ]
        semantic_keys = {
            (evidence.file_path, evidence.line_start, evidence.line_end)
            for evidence in semantic_evidence
        }
        retrieved_evidence = [
            evidence
            for evidence in retrieve_requirement_candidates(
                requirement.title, requirement.skill, files
            )
            if (evidence.file_path, evidence.line_start, evidence.line_end)
            not in detected_keys | semantic_keys
        ]
        retrieved_count += len(retrieved_evidence)
        evidence_list = [*detected_evidence, *semantic_evidence, *retrieved_evidence]
        # Retrieved candidates enrich the AI context but never raise the
        # deterministic verdict or score by themselves.
        strongest = detected_evidence[0] if detected_evidence else None
        if not skill:
            verdict = "unsupported"
            rule_score = 0.0
            explanation = "当前规则尚不支持评估此项要求，未计入分数；不代表用户缺少该能力。"
        elif strongest:
            verdict = "supported" if strongest.strength == "high" else "partial"
            rule_score = STRENGTH_SCORE[strongest.strength]
            explanation = strongest.explanation
            if re.search(
                r"优化|高并发|精通|熟练|性能|调优|optimization|performance", requirement.title, re.I
            ):
                rule_score = min(rule_score, 0.3)
                verdict = "partial"
                explanation += " 当前片段不能证明熟练程度、性能优化或完整业务实现，需进一步核验。"
        elif claim:
            verdict = "claimed_only"
            rule_score = 0.1
            explanation = "简历中存在该技能声明，但项目文件中暂未找到可验证证据"
        else:
            verdict = "gap"
            rule_score = 0.0
            explanation = "简历与项目中均未找到足够信息，当前无法确认该能力"
        if skill:
            total_weight += requirement.weight
            weighted_total += rule_score * requirement.weight
        items.append(
            MatchItemResult(
                requirement_id=requirement.id,
                requirement_title=requirement.title,
                skill=requirement.skill,
                claimed=claim is not None,
                claim_text=claim.claim_text if claim else None,
                evidence=strongest,
                evidence_list=evidence_list,
                verdict=verdict,
                ai_confidence=None,
                rule_base_score=rule_score,
                weight=requirement.weight,
                final_score=round(rule_score * 100, 2) if skill else None,
                explanation=explanation,
                formula_version=FORMULA_VERSION,
            )
        )

    overall_score = round(weighted_total / total_weight * 100, 2) if total_weight else None
    gaps = [item.requirement_title for item in items if item.verdict == "gap"]
    claimed_only = [item.skill for item in items if item.verdict == "claimed_only"]
    verified_count = sum(item.verdict in {"supported", "partial"} for item in items)
    unsupported_count = sum(item.verdict == "unsupported" for item in items)
    summary = (
        f"共{len(items)}项岗位要求，其中{verified_count}项有项目证据支撑，"
        f"{len(claimed_only)}项仅有简历声明，{len(gaps)}项当前无法确认，"
        f"{unsupported_count}项暂不支持评估且不计分。分数为材料支持度，不是能力或录用结论。"
    )
    return MatchResult(
        overall_score,
        items,
        gaps,
        claimed_only,
        summary,
        retrieval_steps=[
            {
                "name": "混合检索补充候选上下文",
                "engine": HYBRID_RETRIEVAL_VERSION,
                "candidateCount": retrieved_count,
                "changesRuleScore": False,
                "semanticEmbedding": False,
            }
        ],
    )
