"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { Page, ReportSummary } from "@/lib/api/domain";
import { reportSummaryText } from "@/lib/report-display";
import { useAuth } from "./AuthProvider";
import { ErrorNotice } from "./AccessGate";
import ListPagination from "./ListPagination";

export function ReportHistoryCard({ report, onSameJob }: { report: ReportSummary; onSameJob?: (jobId: string) => void }) {
  return <article className="panel space-y-3">
    <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0 flex-1"><Link className="break-words text-lg font-semibold text-indigo-800 underline-offset-4 hover:underline" href={`/reports/${report.id}`}>{report.jobTitle}</Link><p className="mt-1 text-sm text-slate-600">{report.candidateName} · {new Date(report.createdAt).toLocaleString("zh-CN")}</p></div>{report.isLatestForJob !== undefined && <span className="rounded bg-slate-100 px-2 py-1 text-sm text-slate-700">{report.isLatestForJob ? "最新" : "有后续报告"}</span>}</div>
    {!!report.materials?.length&&<p className="text-sm text-slate-700">{report.materials.map(m=>`${m.title} v${m.versionNumber}`).join(" · ")}</p>}
    <details className="text-sm text-slate-600"><summary className="cursor-pointer py-1">报告摘要与材料身份</summary><p className="mt-2 whitespace-pre-wrap leading-7">{reportSummaryText(report.summary)}</p>
    {!!report.materials?.length && <details className="text-xs text-slate-600"><summary className="cursor-pointer leading-5">固定材料：{report.materials.map(material => `${material.kind === "resume" ? "简历" : material.materialRole === "reference" ? "参考材料" : "项目"} v${material.versionNumber}`).join(" · ")}</summary><ul className="mt-2 space-y-1">{report.materials.map(material => <li key={`${material.kind}-${material.id}`} className="break-words">{material.title} · 第{material.versionNumber}版 · 材料编号 {material.id.slice(0, 8)}</li>)}</ul></details>}
    </details><div className="flex flex-wrap gap-x-5 gap-y-2 text-sm"><Link className="text-indigo-700 underline" href={`/reports/${report.id}`}>查看报告 →</Link>{onSameJob && <button type="button" className="text-indigo-700 underline" onClick={() => onSameJob(report.jobId)}>同岗位历史{report.jobReportCount !== undefined ? `（${report.jobReportCount}份）` : ""}</button>}</div>
  </article>;
}

export default function ReportList() {
  const { user } = useAuth();
  return <HistoryWorkspace key={user?.id} />;
}
function HistoryWorkspace() {
  const { user } = useAuth();
  const [data, setData] = useState<Page<ReportSummary> | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [filters, setFilters] = useState({ q: "", jobId: "" });
  useEffect(() => {
    const jobId = new URLSearchParams(window.location.search).get("jobId");
    if (jobId) setFilters(previous => ({ ...previous, jobId }));
  }, []);
  useEffect(() => {
    let current = true;
    setError(""); setLoading(true); setData(null);
    api.listReports(page, 20, filters).then(value => { if (current) { setData(value); if (value.page !== page) setPage(value.page); } })
      .catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [revision, page, filters]);
  return <div className="space-y-5"><div className="flex flex-wrap items-end justify-between gap-3"><h1 className="page-title">我的报告</h1><div className="flex flex-wrap gap-3">{user?.role === "student" && <Link className="text-sm text-indigo-700 underline" href="/applications">我的投递</Link>}<Link className="text-sm text-indigo-700 underline" href="/jobs">选择岗位</Link></div></div>
    <form className="panel flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); setPage(1); setFilters(previous => ({ ...previous, q: draft.trim() })); }}><label className="min-w-0 flex-1 text-sm">按岗位名称查找全部报告<input className="field mt-1" type="search" maxLength={200} value={draft} onChange={event => setDraft(event.target.value)} placeholder="输入岗位名称" /></label><button className="btn" disabled={loading}>查找</button>{(filters.q || filters.jobId) && <button className="btn-secondary" type="button" onClick={() => { setDraft(""); setFilters({ q: "", jobId: "" }); setPage(1); }}>查看全部报告</button>}</form>
    {filters.jobId && <p role="status" className="text-sm text-slate-700">正在查看同一岗位的历史报告；各份报告保留生成时固定的材料版本。</p>}
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {loading && <p role="status" className="text-sm text-slate-600">正在加载报告…</p>}
    {!loading && !error && data?.items.length === 0 && <div className="panel space-y-3 text-sm text-slate-600"><p>{filters.q || filters.jobId ? "没有符合条件的报告，可以修改或清除筛选。" : "还没有匹配报告。选择岗位，用已上传的材料生成报告，再决定是否投递。"}</p><Link className="text-indigo-700 underline" href="/jobs">去选择岗位 →</Link></div>}
    <div className="space-y-3" aria-busy={loading}>{data?.items.map((report,index) => <ReportHistoryCard report={report} key={report.id} onSameJob={!filters.jobId&&data.items.findIndex(r=>r.jobId===report.jobId)===index ? jobId => { setDraft(""); setFilters({ q: "", jobId }); setPage(1); } : undefined} />)}</div>
    {data && <ListPagination label="报告分页" value={data} busy={loading} onPage={setPage} />}
  </div>;
}
