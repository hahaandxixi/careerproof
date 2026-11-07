import type { MatchReport, Page, ReportComparison, ReportSummary } from "./api/domain";
import { displayJobTitle, displayMaterialTitle } from "./demo-display-identity.js";

export function sameReportScope(reference: ReportSummary, report: ReportSummary) {
  return report.jobId === reference.jobId && report.candidateId === reference.candidateId;
}
function reportLabelContent(report: ReportSummary) {
  const time = new Date(report.createdAt).toLocaleString("zh-CN", { hour12: false });
  const materials = report.materials?.map(material =>
    `${displayMaterialTitle(material.title || (material.kind === "resume" ? "简历" : "项目"), material.id)} v${material.versionNumber}`,
  ).join(" / ") || "未记录材料版本";
  return `${displayJobTitle(report.jobTitle || "岗位报告", report.jobId)} · ${time} · ${materials}`;
}
export function reportPairLabel(report: ReportSummary, peers: readonly ReportSummary[] = []) {
  const label = reportLabelContent(report);
  const same = peers.filter(row => reportLabelContent(row) === label)
    .sort((a, b) => a.id.localeCompare(b.id));
  return same.length > 1 ? `${label} · 同批第 ${same.findIndex(row => row.id === report.id) + 1} 份` : label;
}
export function reportPairOptionLabel(report: ReportSummary, peers: readonly ReportSummary[] = []) {
  const time = new Date(report.createdAt).toLocaleString("zh-CN", { year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
  const versions = report.materials?.map(material =>
    `${displayMaterialTitle(material.title || (material.kind === "resume" ? "简历" : "项目"), material.id)} v${material.versionNumber}`,
  ).join(" / ") || "未记录材料版本";
  const same = peers.filter(row =>
    new Date(row.createdAt).getTime() === new Date(report.createdAt).getTime()
    && JSON.stringify(row.materials?.map(m => [m.kind, m.versionNumber]))
      === JSON.stringify(report.materials?.map(m => [m.kind, m.versionNumber])),
  ).sort((a, b) => a.id.localeCompare(b.id));
  const duplicate = same.length > 1 ? ` · 同批第 ${same.findIndex(row => row.id === report.id) + 1} 份` : "";
  return `${time} · ${versions}${duplicate}`;
}
export type ReportPairValue = { comparison: ReportComparison; base: MatchReport; current: MatchReport };
export type ReportPairState = {
  reports: ReportSummary[]; page: number; hasMore: boolean; listing: boolean;
  baseId: string; targetId: string; busy: boolean; error: string; value: ReportPairValue | null;
};
type PairApi = {
  listReports(page: number, size: number, filters: { jobId: string; scope: "all" }): Promise<Page<ReportSummary>>;
  getReport(id: string): Promise<MatchReport>;
  compareReports(baseId: string, targetId: string): Promise<ReportComparison>;
  errorMessage(error: unknown): string;
};
export function createReportPairSession(
  reference: MatchReport, api: PairApi, publish: (state: ReportPairState) => void,
  initialBaseId = "",
) {
  let active = true, listEpoch = 0, compareEpoch = 0;
  let state: ReportPairState = {
    reports: [reference], page: 0, hasMore: true, listing: false,
    baseId: initialBaseId && initialBaseId !== reference.id ? initialBaseId : "",
    targetId: reference.id, busy: false, error: "", value: null,
  };
  const emit = (patch: Partial<ReportPairState>) => { if (active) { state = { ...state, ...patch }; publish(state); } };
  return {
    activate() { active = true; emit({ listing: false, busy: false }); },
    dispose() { active = false; listEpoch++; compareEpoch++; state = { ...state, listing: false, busy: false }; },
    select(side: "baseId" | "targetId", id: string) {
      compareEpoch++;
      emit({ [side]: id, busy: false, error: "", value: null });
    },
    async loadMore() {
      if (!active || state.listing || !state.hasMore) return;
      const ticket = ++listEpoch, page = state.page + 1;
      emit({ listing: true, error: "" });
      try {
        const result = await api.listReports(page, 50, { jobId: reference.jobId, scope: "all" });
        if (!active || ticket !== listEpoch) return;
        const reports = [...new Map([...state.reports, ...result.items.filter(report => sameReportScope(reference, report))].map(report => [report.id, report])).values()];
        emit({ reports, page: result.page, hasMore: result.page * result.pageSize < result.total,
          baseId: state.baseId || reports.find(report => report.id !== state.targetId)?.id || "" });
      } catch (error) { if (ticket === listEpoch) emit({ error: api.errorMessage(error) }); }
      finally { if (ticket === listEpoch) emit({ listing: false }); }
    },
    async compare() {
      const { baseId, targetId } = state;
      if (!baseId || !targetId || baseId === targetId) { emit({ error: "请选择两份不同的报告。", value: null }); return; }
      if (![baseId, targetId].every(id => state.reports.some(report => report.id === id && sameReportScope(reference, report)))) return;
      const ticket = ++compareEpoch;
      emit({ busy: true, error: "", value: null });
      try {
        const [comparison, base, current] = await Promise.all([api.compareReports(baseId, targetId), api.getReport(baseId), api.getReport(targetId)]);
        if (!active || ticket !== compareEpoch) return;
        if (base.id !== baseId || current.id !== targetId || comparison.baseId !== baseId || comparison.targetId !== targetId || !sameReportScope(reference, base) || !sameReportScope(reference, current)) throw new Error("报告身份或岗位不一致，已停止显示对照。");
        emit({ value: { comparison, base, current } });
      } catch (error) { if (ticket === compareEpoch) emit({ error: api.errorMessage(error) }); }
      finally { if (ticket === compareEpoch) emit({ busy: false }); }
    },
  };
}
