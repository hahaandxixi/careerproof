import type { ReportItem } from "./api/domain";

export function invalidNarrativeCitations(item: Pick<ReportItem, "aiExplanation" | "aiInformationGap" | "aiSuggestion" | "aiCitationIds" | "evidenceList">): string[] {
  const allowed = new Set(item.evidenceList.map(e => e.citationId).filter(Boolean));
  const structured = new Set(item.aiCitationIds);
  const found = [item.aiExplanation, item.aiInformationGap, item.aiSuggestion].join(" ").match(/\bR\d+-E\d+\b/g) ?? [];
  return [...new Set([...found, ...item.aiCitationIds].filter(id => !allowed.has(id) || !structured.has(id)))];
}
