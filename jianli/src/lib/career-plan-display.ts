import type { CareerPlanResult, JobRecommendation } from "./api/domain.ts";

export function careerPlanRecommendations(
  result: Pick<CareerPlanResult, "recommendations" | "aiPlan" | "aiValidationIssues">,
  expanded: boolean,
): JobRecommendation[] {
  if (expanded) return result.recommendations;
  const comparedIds = new Set(result.aiPlan?.advice.map(advice => advice.jobId) ?? []);
  if (result.aiPlan?.focusJobId) comparedIds.add(result.aiPlan.focusJobId);
  const hasComparedCandidate = result.recommendations.some(item => comparedIds.has(item.jobId));
  if (!hasComparedCandidate) result.recommendations.slice(0, 3).forEach(item => comparedIds.add(item.jobId));
  // Rejected outputs still need their current evidence visible for inspection.
  const diagnosticIds = new Set(
    result.aiValidationIssues?.flatMap(issue => issue.citationIds) ?? [],
  );
  const relevant = result.recommendations.filter(item =>
    comparedIds.has(item.jobId)
    || item.evidence.some(evidence => evidence.citationId && diagnosticIds.has(evidence.citationId)),
  );
  return relevant;
}
