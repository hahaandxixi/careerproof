import type { CareerPlanResult, ReportSummary } from "./api/domain";

export function planMatchesReport(plan: CareerPlanResult, report: Pick<ReportSummary, "jobId" | "materials">, jobId: string) {
  if (report.jobId !== jobId || !report.materials || !plan.materials.length) return false;
  if ([...plan.materials, ...report.materials].some(m => !m.id || !m.contentHash)) return false;
  const key = (m: { kind: string; id: string; contentHash: string }) => `${m.kind}:${m.id}:${m.contentHash}`;
  const a = plan.materials.map(key).sort();
  const b = report.materials.map(key).sort();
  return a.length === b.length && a.every((value, i) => value === b[i]);
}
