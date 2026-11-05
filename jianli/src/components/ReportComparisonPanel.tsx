"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import { createReportPairSession, reportPairLabel, type ReportPairState } from "@/lib/report-pair";
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
    <h2 className="text-lg font-semibold">报告 A / B 对比</h2>
    <p className="reading-copy">只比较本人同一岗位的两份已保存报告。上传新材料不等于生成新报告；本操作只读，历史报告与原投递不变。A 为基准，B 为目标，不限定时间先后。</p>
    {state && <div className="grid min-w-0 gap-4 lg:grid-cols-2">{([['baseId', '报告 A · 基准'], ['targetId', '报告 B · 目标']] as const).map(([side, label]) => <label className="min-w-0 space-y-2" key={side}><span className="block font-semibold">{label}</span><select className="field" value={state[side]} onChange={event => session.select(side, event.target.value)}><option value="">请选择报告</option>{state.reports.map(option => <option key={option.id} value={option.id} disabled={option.id === state[side === 'baseId' ? 'targetId' : 'baseId']}>{reportPairLabel(option)}</option>)}</select><span className="block break-words text-sm leading-7 text-slate-600">{state.reports.find(option => option.id === state[side]) ? reportPairLabel(state.reports.find(option => option.id === state[side])!) : '尚未选择'}</span></label>)}</div>}
    <div className="flex flex-wrap gap-3"><button className="btn-secondary" disabled={!state?.baseId || !state.targetId || state.baseId === state.targetId || state.busy} onClick={() => void session.compare()}>{state?.busy ? "读取对比…" : "对比所选报告"}</button>{(!state || state.hasMore) && <button type="button" className="btn-secondary" disabled={state?.listing} onClick={() => void session.loadMore()}>{!state || state.listing ? "读取同岗位报告…" : "加载更多同岗位报告"}</button>}</div>
    {state?.error && <p role="alert" className="text-sm text-rose-700">{state.error}</p>}
    {state && !state.listing && state.reports.length < 2 && <p className="text-sm text-slate-600">尚无同一岗位的第二份报告。完成补证并重新分析后，再选择两份报告。</p>}
    {value && <ReportComparisonView key={`${value.comparison.baseId}:${value.comparison.targetId}`} value={value.comparison} base={value.base} current={value.current} />}
  </section>;
}
