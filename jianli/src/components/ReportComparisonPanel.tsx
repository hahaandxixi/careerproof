"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import { createReportPairSession, reportPairLabel, reportPairOptionLabel, type ReportPairState } from "@/lib/report-pair";
import ReportComparisonView from "./ReportComparisonView";

export default function ReportComparisonPanel({ report, initialBaseId = "", origin = "", revision }: { report: MatchReport; initialBaseId?: string; origin?: string; revision: string }) {
  return <ReportPairPicker key={`${report.candidateId}:${report.jobId}:${report.id}:${revision}`} report={report} initialBaseId={initialBaseId} origin={origin} />;
}
function ReportPairPicker({ report, initialBaseId, origin }: { report: MatchReport; initialBaseId: string; origin: string }) {
  const [state, setState] = useState<ReportPairState | null>(null);
  const session = useMemo(() => createReportPairSession(report, { listReports: api.listReports, getReport: api.getReport, compareReports: api.compareReports, errorMessage }, setState, initialBaseId), [report, initialBaseId]);
  useEffect(() => { session.activate(); void session.loadMore(); return () => session.dispose(); }, [session]);
  const value = state?.value;
  return <section className="panel min-w-0 space-y-3">
    <h2 className="text-lg font-semibold">报告版本对比</h2>
    <div className="report-pair-controls">
      {state && ([["baseId", "A 基准报告"], ["targetId", "B 对照报告"]] as const).map(([side, label]) => <label className="min-w-0 space-y-1" key={side}><span className="block font-semibold">{label}</span><select className="field w-full" value={state[side]} onChange={event => session.select(side, event.target.value)}><option value="">请选择报告</option>{state.reports.map(option => <option key={option.id} value={option.id} disabled={option.id === state[side === "baseId" ? "targetId" : "baseId"]} title={reportPairLabel(option, state.reports)}>{reportPairOptionLabel(option, state.reports)}</option>)}</select></label>)}
      <button type="button" className="btn" disabled={!state?.baseId || !state.targetId || state.baseId === state.targetId || state.busy} onClick={() => void session.compare()}>{state?.busy ? "读取对比…" : "对比所选报告"}</button>
    </div>
    {(value || !state || state.hasMore) && <div className="flex flex-wrap items-center gap-3">
      {value && <span className="text-sm font-medium text-[#1d4a40]" role="status">当前结果：A → B</span>}
      {(!state || state.hasMore) && <button type="button" className="btn-quiet btn-compact" disabled={state?.listing} onClick={() => void session.loadMore()}>{!state || state.listing ? "读取同岗位报告…" : "加载更多报告"}</button>}
    </div>}
    {state?.error && <p role="alert" className="text-sm text-rose-700">{state.error}</p>}
    {state && !state.listing && !state.error && state.reports.length < 2 && <p className="text-sm text-slate-600">该岗位暂无其他可比较报告。</p>}
    {value && <ReportComparisonView key={`${value.comparison.baseId}:${value.comparison.targetId}`} value={value.comparison} base={value.base} current={value.current} origin={origin} />}
  </section>;
}
