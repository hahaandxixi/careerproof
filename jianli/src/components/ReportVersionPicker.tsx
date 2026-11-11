"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { MatchReport, ReportSummary } from "@/lib/api/domain";
import { reportOrigin, reportVersionHref } from "@/lib/report-navigation";
import { reportPairOptionLabel } from "@/lib/report-pair";

const PAGE_SIZE = 20;

export default function ReportVersionPicker({ report, origin }: { report: MatchReport; origin: string }) {
  const scope = reportOrigin(origin).scope;
  return <Picker key={`${report.id}:${scope}`} report={report} origin={origin} scope={scope} />;
}

function Picker({ report, origin, scope }: { report: MatchReport; origin: string; scope: "all" | "product" }) {
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<{ page: number; rows: ReportSummary[]; total: number }>();
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState("");
  const { jobId, candidateId } = report;
  const read = useCallback((page: number) => api.listReports(page, PAGE_SIZE, { jobId, scope }), [jobId, scope]);
  useEffect(() => {
    let active = true;
    read(page).then(result => {
      if (!active) return;
      const rows = result.items.filter(row => row.jobId === jobId && row.candidateId === candidateId);
      setData(previous => ({
        page: result.page,
        rows: page === 1 ? rows : [...new Map([...(previous?.rows ?? []), ...rows].map(row => [row.id, row])).values()],
        total: result.total,
      }));
      setError("");
    }, reason => { if (active) setError(errorMessage(reason)); });
    return () => { active = false; };
  }, [read, page, revision, jobId, candidateId]);
  const rows = data?.rows ?? [];
  const latest = rows.find(row => row.isLatestForJob);
  const historical = !!latest && latest.id !== report.id;
  const peers = rows.some(row => row.id === report.id) ? rows : [report, ...rows];
  return <div className="report-version-tools">
    {historical && <p className="text-sm font-medium">正在查看历史报告</p>}
    <div className="flex flex-wrap items-center gap-2">
      {rows.some(row => row.id !== report.id) && <Link className="action-link" href={reportVersionHref(report.id, origin, "#report-comparison")}>版本对比</Link>}
      <button type="button" className="btn-secondary" aria-expanded={open} aria-controls="report-version-picker" onClick={() => setOpen(value => !value)}>切换版本</button>
    </div>
    <div id="report-version-picker" hidden={!open} className="mt-2 min-w-0 space-y-2">
      <p className="text-sm break-words">当前：{reportPairOptionLabel(report, peers)}</p>
      {error && <p role="alert" className="text-sm">暂时无法读取报告版本。<button type="button" className="action-link ml-2" onClick={() => { setError(""); setRevision(value => value + 1); }}>重试</button></p>}
      {!error && data?.page !== page && <p role="status">正在读取报告版本…</p>}
      {data && rows.every(row => row.id === report.id) && data.page * PAGE_SIZE >= data.total && <p className="text-sm">当前范围没有其他版本。</p>}
      {rows.some(row => row.id !== report.id) && <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-0 flex-1 text-sm">选择已保存版本
          <select className="field mt-1" value={choice} onChange={event => setChoice(event.target.value)}>
            <option value="">请选择</option>
            {rows.filter(row => row.id !== report.id).map(row => <option key={row.id} value={row.id}>{row.isLatestForJob ? "最新 · " : "历史 · "}{reportPairOptionLabel(row, peers)}</option>)}
          </select>
        </label>
        {choice && <Link className="btn-secondary" href={reportVersionHref(choice, origin)}>打开所选版本</Link>}
      </div>}
      {historical && <Link className="action-link" href={reportVersionHref(latest.id, origin)}>回到最新报告</Link>}
      {data && data.page * PAGE_SIZE < data.total && <button type="button" className="btn-secondary" disabled={!!error || page !== data.page} onClick={() => setPage(data.page + 1)}>加载更多版本</button>}
    </div>
  </div>;
}
