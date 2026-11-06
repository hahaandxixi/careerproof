"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import { createReportPairSession, reportPairLabel, reportPairOptionLabel, type ReportPairState } from "@/lib/report-pair";
import { displayJobTitle } from "@/lib/demo-display-identity.js";
import ReportComparisonView from "./ReportComparisonView";

export default function ReportComparisonPanel({ report, revision }: { report: MatchReport; revision: string }) {
  return <ReportPairPicker key={`${report.candidateId}:${report.jobId}:${report.id}:${revision}`} report={report} />;
}
function ReportPairPicker({ report }: { report: MatchReport }) {
  const [state, setState] = useState<ReportPairState | null>(null);
  const session = useMemo(() => createReportPairSession(report, { listReports: api.listReports, getReport: api.getReport, compareReports: api.compareReports, errorMessage }, setState), [report]);
  useEffect(() => { session.activate(); void session.loadMore(); return () => session.dispose(); }, [session]);
  const value = state?.value;
  return <section className="panel min-w-0 space-y-4">
    <h2 className="text-lg font-semibold">报告版本对比<span className="ml-3 text-sm font-normal text-slate-600">{displayJobTitle(report.jobTitle, report.jobId)}</span></h2>
    <p className="reading-copy">只读比较同一岗位的已保存报告，不改动历史记录或原投递。</p>
    {state && <div className="grid min-w-0 gap-4 lg:grid-cols-2">{([['baseId', '基准报告 A'], ['targetId', '对照报告 B']] as const).map(([side, label]) => <label className="min-w-0 space-y-2" key={side}><span className="block font-semibold">{label}</span><select className="field" value={state[side]} onChange={event => session.select(side, event.target.value)}><option value="">请选择报告</option>{state.reports.map(option => <option key={option.id} value={option.id} disabled={option.id === state[side === 'baseId' ? 'targetId' : 'baseId']} title={reportPairLabel(option, state.reports)}>{reportPairOptionLabel(option, state.reports)}</option>)}</select></label>)}</div>}
    <div className="flex flex-wrap gap-3"><button className="btn-secondary" disabled={!state?.baseId || !state.targetId || state.baseId === state.targetId || state.busy} onClick={() => void session.compare()}>{state?.busy ? "读取对比…" : "对比所选报告"}</button>{(!state || state.hasMore) && <button type="button" className="btn-secondary" disabled={state?.listing} onClick={() => void session.loadMore()}>{!state || state.listing ? "读取同岗位报告…" : "加载更多同岗位报告"}</button>}</div>
    {state?.error && <p role="alert" className="text-sm text-rose-700">{state.error}</p>}
    {state && !state.listing && !state.error && state.reports.length < 2 && <p className="text-sm text-slate-600">该岗位暂无其他可比较报告。</p>}
    {value && <><p className="text-sm text-slate-600">当前结果：A {reportPairOptionLabel(value.base)} → B {reportPairOptionLabel(value.current)}</p><ReportComparisonView key={`${value.comparison.baseId}:${value.comparison.targetId}`} value={value.comparison} base={value.base} current={value.current} /></>}
  </section>;
}
