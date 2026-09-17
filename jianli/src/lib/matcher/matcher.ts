import type {
  EvidenceStrength,
  Job,
  MatchItem,
  MatchResult,
  ProjectFile,
  SkillClaim,
  Verdict,
} from "../types";
import { findEvidence } from "../analyzer/codeAnalyzer";

/**
 * 可追溯匹配器（真实规则逻辑，非 LLM）
 *
 * 输出「证据链」而非单薄分数：
 *   岗位要求 → 候选人能力声明 → 代码证据 → 证据强度 → 缺失内容
 * 这是本项目的核心差异化：匹配结果可追溯、可点击查看依据。
 */

const STRENGTH_SCORE: Record<EvidenceStrength, number> = {
  high: 1.0,
  medium: 0.8,
  low: 0.65,
};

function decideVerdict(claimed: boolean, hasEvidence: boolean): Verdict {
  if (hasEvidence) return "verified";
  if (claimed) return "claimed_only";
  return "gap";
}

function itemScore(verdict: Verdict, strength?: EvidenceStrength): number {
  if (verdict === "verified" && strength) return STRENGTH_SCORE[strength];
  if (verdict === "claimed_only") return 0.4;
  return 0;
}

/** 计算候选人与岗位的可追溯匹配结果（纯函数） */
export function matchCandidate(
  job: Job,
  claims: SkillClaim[],
  allFiles: ProjectFile[],
  candidateId: string
): MatchResult {
  const claimBySkill = new Map(claims.map((c) => [c.skill, c]));

  const items: MatchItem[] = job.requirements.map((req) => {
    const claim = claimBySkill.get(req.skill);
    const evidenceList = findEvidence(allFiles, req.skill);
    const evidence = evidenceList[0] ?? null;
    const verdict = decideVerdict(!!claim, !!evidence);

    return {
      requirementId: req.id,
      requirementTitle: req.title,
      skill: req.skill,
      claimed: !!claim,
      claimText: claim?.claimText,
      evidence,
      evidenceList,
      verdict,
      score: itemScore(verdict, evidence?.strength),
    };
  });

  const totalWeight = job.requirements.reduce((s, r) => s + r.weight, 0) || 1;
  const weighted = items.reduce(
    (sum, it, i) => sum + it.score * job.requirements[i].weight,
    0
  );
  const overallScore = Math.round((weighted / totalWeight) * 100);

  const gaps = items.filter((i) => i.verdict === "gap").map((i) => i.requirementTitle);
  const claimedOnly = items
    .filter((i) => i.verdict === "claimed_only")
    .map((i) => i.skill);

  const verifiedCount = items.filter((i) => i.verdict === "verified").length;
  const summary =
    `共 ${items.length} 项要求，其中 ${verifiedCount} 项有代码证据支撑，` +
    `${claimedOnly.length} 项仅简历声明未验证，${gaps.length} 项存在能力缺口。`;

  return {
    jobId: job.id,
    candidateId,
    overallScore,
    items,
    gaps,
    claimedOnly,
    summary,
  };
}
