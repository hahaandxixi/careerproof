import type { ReportComparison } from "./api/domain";

type ComparisonItem = ReportComparison["items"][number];

export function enterpriseQuestionReview(item: ComparisonItem) {
  const personalEvidence = item.addedEvidence.filter(evidence => evidence.provenance !== "reference");
  const referenceEvidence = item.addedEvidence.filter(evidence => evidence.provenance === "reference");
  return {
    personalEvidenceCount: personalEvidence.length,
    referenceEvidenceCount: referenceEvidence.length,
    criterionChanged: item.status !== "existing" || item.changes.includes("requirement"),
    remainingGap: item.targetInformationGap?.trim() || null,
  };
}
