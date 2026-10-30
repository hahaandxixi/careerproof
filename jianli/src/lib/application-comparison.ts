import type { ApplicationView } from "./api/client";

/** Snapshot basis plus actual axes must agree; never align unlike requirements by position. */
export function comparableRadarAxes(a: ApplicationView, b: ApplicationView): boolean {
  if (a.fixedRequirementBasisComplete!==true || b.fixedRequirementBasisComplete!==true) return false;
  if (!a.comparisonBasis || a.comparisonBasis !== b.comparisonBasis || a.jobId !== b.jobId ||
      !a.dimensions.length || a.dimensions.length !== b.dimensions.length) return false;
  const keys = new Set(a.dimensions.map(d => d.requirementId));
  if (keys.size !== a.dimensions.length || new Set(b.dimensions.map(d => d.requirementId)).size !== keys.size) return false;
  return a.dimensions.every(d => {
    const other = b.dimensions.find(value => value.requirementId === d.requirementId);
    return other && ["title", "skill", "weight", "formulaVersion", "evidenceLevelVersion"].every(key =>
      d[key as keyof typeof d] === other[key as keyof typeof other]);
  });
}

export function mixedComparisonBasis(items: ApplicationView[]): boolean {
  return items.length > 1 && (
    items.some(item => !item.comparisonBasis) ||
    new Set(items.map(item => item.comparisonBasis)).size > 1
  );
}

export function filterApplications(
  items: ApplicationView[], query: string, focus: string, verdict: string,
): ApplicationView[] {
  const mixed = mixedComparisonBasis(items);
  const keyword = query.trim().toLocaleLowerCase();
  return items.filter(item => {
    const text = `${item.candidateName} ${item.dimensions.map(d => `${d.skill} ${d.title}`).join(" ")}`;
    const dimensions = focus ? item.dimensions.filter(d => d.requirementId === focus) : item.dimensions;
    const matchesVerdict = !verdict || dimensions.some(d => verdict === "supported"
      ? ["supported", "partial", "verified"].includes(d.verdict) : d.verdict === verdict);
    return text.toLocaleLowerCase().includes(keyword) && matchesVerdict;
  }).sort((a, b) => {
    if (mixed) return b.createdAt.localeCompare(a.createdAt);
    const score = (item: ApplicationView) => focus
      ? item.dimensions.find(d => d.requirementId === focus)?.score : item.overallScore;
    return (score(b) ?? -1) - (score(a) ?? -1) || b.createdAt.localeCompare(a.createdAt);
  });
}

/** Keep the filtered list, its empty state and an already-open report in sync. */
export function applicationFilterView(
  items: ApplicationView[], query: string, focus: string, verdict: string,
  selectedId?: string,
) {
  const visible = filterApplications(items, query, focus, verdict);
  return {
    visible,
    empty: visible.length === 0,
    selectedOutside: !!selectedId && !visible.some(item => item.id === selectedId),
  };
}
