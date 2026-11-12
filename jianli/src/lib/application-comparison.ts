import type { ReportItem } from "./api/domain";
import type { ApplicationView } from "./api/client";
import { isMaterialGap } from "./verdict-display.js";

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
    items.some(item=>item.fixedRequirementBasisComplete!==true) ||
    items.some(item => !item.comparisonBasis) ||
    new Set(items.map(item => item.comparisonBasis)).size > 1
  );
}

/** Keep one mutually-comparable group for the same-scale surface; leave unlike/incomplete reports out. */
export function comparableApplicationGroup(items: ApplicationView[]) {
  const groups: ApplicationView[][] = [];
  for (const item of items) {
    const group = groups.find(candidate => comparableRadarAxes(candidate[0], item));
    if (group) group.push(item);
    else groups.push([item]);
  }
  const comparable = groups
    .filter(group => group.length > 1)
    .sort((a, b) => b.length - a.length || (a[0]?.createdAt ?? "").localeCompare(b[0]?.createdAt ?? ""))[0] ?? [];
  const ids = new Set(comparable.map(item => item.id));
  return { comparable, excluded: items.filter(item => !ids.has(item.id)) };
}

export function filterApplications(
  items: ApplicationView[], query: string, focus: string, verdict: string,
): ApplicationView[] {
  const mixed = mixedComparisonBasis(items);
  const keyword = query.trim().toLocaleLowerCase();
  return items.filter(item => {
    const text = `${item.candidateName} ${item.dimensions.map(d => `${d.skill} ${d.title}`).join(" ")}`;
    const dimensions = focus ? item.dimensions.filter(d => d.requirementId === focus) : item.dimensions;
    const matchesVerdict = !verdict || dimensions.some(d => {
      if (verdict === "supported_only") return d.verdict === "supported" || d.verdict === "verified";
      if (verdict === "needs_material") return isMaterialGap(d.verdict);
      return verdict === "supported" ? ["supported", "partial", "verified"].includes(d.verdict) : d.verdict === verdict;
    });
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


/** Only displayed fields are compared. Equal counts never identify equal sources. */
export function requirementDifference(
  first: Pick<ReportItem, "verdict" | "finalScore" | "evidenceList">,
  second: Pick<ReportItem, "verdict" | "finalScore" | "evidenceList">,
  compareSupport: boolean,
): string {
  const fields: { name: string; first: string | number | null; second: string | number | null }[] = [
    { name: "判断状态", first: first.verdict, second: second.verdict },
    { name: "来源数量", first: first.evidenceList.length, second: second.evidenceList.length },
  ];
  if (compareSupport) fields.push({ name: "材料支持度指数", first: first.finalScore, second: second.finalScore });
  const differences = fields.filter(field => field.first !== field.second).map(field => field.name);
  return differences.length
    ? differences.join("、") + "不同，请分别核对两份固定报告。"
    : "可见的" + fields.map(field => field.name).join("、") + "相同，仍需分别核对来源。";
}
