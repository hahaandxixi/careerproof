import type { MatchReport } from "./api/domain";

type ReviewStatus = "pending" | "accepted" | "rejected" | "corrected";
export type ReviewIssue = { message: string; outcome: "rejected" | "unknown" | "saved"; readRequired: boolean };
export type ReportReviewState = {
  report: MatchReport | null; error: string; reviewing: string | null;
  issues: Record<string, ReviewIssue>; needsSync: boolean;
};
export const initialReportReviewState: ReportReviewState = { report: null, error: "", reviewing: null, issues: {}, needsSync: false };

/** One write/read cycle at a time. A failed read never repeats a successful or uncertain write. */
export function createReportReviewSession(reportId: string, api: {
  get(id: string): Promise<MatchReport>;
  review(id: string, requirementId: string, status: ReviewStatus, note?: string): Promise<unknown>;
  errorMessage(error: unknown): string;
}, publish: (state: ReportReviewState) => void) {
  let generation = 0, active = false, locked = false;
  let state: ReportReviewState = { ...initialReportReviewState, issues: {} };
  const update = (patch: Partial<ReportReviewState>) => { state = { ...state, ...patch }; publish(state); };
  const current = (ticket: number) => active && generation === ticket;
  const statusOf = (error: unknown) => (error as { status?: number } | null)?.status;
  const denied = (error: unknown) => [401, 403, 404].includes(statusOf(error) ?? 0);
  const issue = (requirementId: string, value: ReviewIssue) => update({ issues: { ...state.issues, [requirementId]: value }, needsSync: value.readRequired });
  async function read(ticket: number) {
    const report = await api.get(reportId);
    if (!current(ticket)) return null;
    if (report.id !== reportId) throw Object.assign(new Error("报告身份不匹配，请重新打开报告。"), { status: 403 });
    return report;
  }
  function accessFailure(error: unknown) {
    update({ report: null, error: api.errorMessage(error), issues: {}, needsSync: false });
  }
  return {
    activate() { active = true; generation++; locked = false; },
    dispose() { active = false; generation++; locked = false; },
    async load() {
      if (!active || locked) return;
      locked = true; const ticket = generation;
      update({ error: "" });
      try { const report = await read(ticket); if (report) update({ report, issues: {}, needsSync: false }); }
      catch (error) { if (current(ticket)) accessFailure(error); }
      finally { if (current(ticket)) locked = false; }
    },
    async review(requirementId: string, status: ReviewStatus, note?: string) {
      if (!active || locked || state.needsSync || !state.report) return;
      locked = true; const ticket = generation;
      update({ reviewing: requirementId });
      try {
        try { await api.review(reportId, requirementId, status, note); }
        catch (error) {
          if (!current(ticket)) return;
          if (denied(error)) { accessFailure(error); return; }
          const code = statusOf(error);
          const uncertain = code === undefined || code < 400 || code === 408 || code >= 500;
          issue(requirementId, { outcome: uncertain ? "unknown" : "rejected", readRequired: uncertain,
            message: uncertain ? `提交结果尚未确认：${api.errorMessage(error)}。请先重新读取核对记录。` : `核对未保存：${api.errorMessage(error)}。可调整后重新提交。` });
          return;
        }
        if (!current(ticket)) return;
        try {
          const report = await read(ticket);
          if (report) { const issues = { ...state.issues }; delete issues[requirementId]; update({ report, issues, needsSync: false }); }
        } catch (error) {
          if (!current(ticket)) return;
          if (denied(error)) { accessFailure(error); return; }
          issue(requirementId, { outcome: "saved", readRequired: true, message: `核对已保存，最新报告暂时读取失败：${api.errorMessage(error)}。请重新读取，无需再次提交。` });
        }
      } finally { if (current(ticket)) { locked = false; update({ reviewing: null }); } }
    },
    async refresh(requirementId: string) {
      if (!active || locked || !state.report) return;
      locked = true; const ticket = generation;
      update({ reviewing: requirementId });
      try {
        const report = await read(ticket);
        if (report) { const issues = { ...state.issues }; delete issues[requirementId]; update({ report, issues, needsSync: false }); }
      } catch (error) {
        if (!current(ticket)) return;
        if (denied(error)) accessFailure(error);
        else issue(requirementId, { outcome: state.issues[requirementId]?.outcome ?? "unknown", readRequired: true, message: `核对记录暂时无法同步：${api.errorMessage(error)}。请重新读取后再提交。` });
      } finally { if (current(ticket)) { locked = false; update({ reviewing: null }); } }
    },
  };
}
