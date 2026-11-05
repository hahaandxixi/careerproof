import type { MatchReport, Page, ReportComparison, ReportSummary } from "./api/domain";

export function sameReportScope(reference: ReportSummary, report: ReportSummary) {
  return report.jobId === reference.jobId && report.candidateId === reference.candidateId;
}
export function reportPairLabel(report: ReportSummary) {
  const mode = report.aiFallbackUsed ? "AI 回退 · 规则结果" : report.analysisMode === "rules" ? "规则分析" : ["ai_evidence", "ai_evidence_manual"].includes(report.analysisMode) ? "AI 证据分析" : report.analysisMode;
  const materials = report.materials?.map(material => `${material.kind === "resume" ? "简历" : "项目"} V${material.versionNumber}(${material.id.slice(0, 8)})`).join(" / ") || "未保存版本信息";
  return `${new Date(report.createdAt).toLocaleString("zh-CN")} · ${report.id.slice(0, 8)} · ${mode} · ${materials}`;
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
export function createReportPairSession(reference: MatchReport, api: PairApi, publish: (state: ReportPairState) => void) {
  let active = true, listEpoch = 0, compareEpoch = 0;
  let state: ReportPairState = { reports: [reference], page: 0, hasMore: true, listing: false, baseId: "", targetId: reference.id, busy: false, error: "", value: null };
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
