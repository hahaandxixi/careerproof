import type { ReportItem } from "./api/domain.ts";

export function evidenceWorkspace(items: ReportItem[]) {
  const supported = items.filter(item => ["supported", "verified"].includes(item.verdict) && !["rejected", "corrected"].includes(item.confirmationStatus ?? ""));
  const partial = items.filter(item => item.verdict === "partial" && !["rejected", "corrected"].includes(item.confirmationStatus ?? ""));
  const gaps = items.filter(item => ["gap", "claimed_only"].includes(item.verdict) && !["rejected", "corrected"].includes(item.confirmationStatus ?? ""));
  const other = items.filter(item => !supported.includes(item) && !partial.includes(item) && !gaps.includes(item));
  // Keep report order for equal priority; never calculate an ability score.
  const priorities = items.filter(item => gaps.includes(item) || partial.includes(item)).sort((a, b) => b.weight - a.weight);
  return { supported, partial, gaps, other, priorities };
}
