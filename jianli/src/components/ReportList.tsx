"use client";
import { displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import IdentityName from "./IdentityName";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { Page, ReportSummary } from "@/lib/api/domain";
import { reportSummaryText } from "@/lib/report-display";
import { useAuth } from "./AuthProvider";
import { ErrorNotice } from "./AccessGate";
import ListPagination from "./ListPagination";

export function ReportHistoryCard({ report, onSameJob }: { report: ReportSummary; onSameJob?: (jobId: string) => void }) {
  const latest = report.isLatestForJob === true;
  const history = report.isLatestForJob === false;
  return <article className={`workspace-row report-record ${latest ? "is-latest" : history ? "is-history" : "is-record"}`}>
    {report.recordProvenance === "test_fixture" && <p className="report-history-flag">历史核验资料 · 非真实招聘岗位</p>}
    <div className="report-record-head">
      <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><Link className="report-record-title" href={`/reports/${report.id}`}>{displayJobTitle(report.jobTitle, report.jobId)}</Link>{latest && <span className="status-chip report-latest-chip">最新报告</span>}</div>
        <p className="mt-1 text-sm text-slate-600"><IdentityName name={report.candidateName} identityId={report.candidateId}/> · {new Date(report.createdAt).toLocaleString("zh-CN")}{latest && report.materials?.length ? ` · ${report.materials.map(m=>`${displayMaterialTitle(m.title, m.id)} v${m.versionNumber}`).join(" · ")}` : ""}</p>
      </div>
      {history && <span className="report-followup-mark">有后续报告</span>}
    </div>
    <details className="report-record-details text-sm text-slate-600"><summary className="disclosure">报告详情</summary><p className="mt-2 whitespace-pre-wrap leading-7">{reportSummaryText(report.summary)}</p>
      {!latest && !!report.materials?.length && <ul className="mt-3 space-y-1 text-xs leading-5">{report.materials.map(material => <li key={`${material.kind}-${material.id}`} className="break-words">{displayMaterialTitle(material.title, material.id)} · 第{material.versionNumber}版 · 材料编号 {material.id.slice(0, 8)}</li>)}</ul>}
    </details>
    <div className="card-actions report-record-actions"><Link className="btn" href={`/reports/${report.id}`}>查看报告</Link>
      {report.jobReportCount !== undefined && report.jobReportCount > 1 && <Link className="btn-secondary" href={`/reports/${report.id}#report-comparison`}>版本对比</Link>}
      {onSameJob && <button type="button" className="btn-quiet" onClick={() => onSameJob(report.jobId)}>同岗位报告{report.jobReportCount !== undefined ? ` · ${report.jobReportCount}份` : ""}</button>}
    </div>
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
  const [includeAudit, setIncludeAudit] = useState(false);
  useEffect(() => {
    const jobId = new URLSearchParams(window.location.search).get("jobId");
    if (jobId) setFilters(previous => ({ ...previous, jobId }));
  }, []);
  useEffect(() => {
    let current = true;
    setError(""); setLoading(true); setData(null);
    api.listReports(page, 20, { ...filters, scope: includeAudit ? "all" : "product" }).then(value => { if (current) { setData(value); if (value.page !== page) setPage(value.page); } })
      .catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [revision, page, filters, includeAudit]);
  return <div className="report-workspace space-y-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="page-title">我的报告</h1><p className="workspace-meta">最新报告与同岗位版本集中在这里，选择报告继续核对或投递。</p></div><div className="flex flex-wrap gap-2">{user?.role === "student" && <><Link className="btn-quiet" href="/skills">个人技能全景</Link><Link className="btn-secondary" href="/applications">我的投递</Link></>}<Link className="btn-secondary" href="/jobs">选择岗位</Link></div></div>
    <form className="report-searchbar" role="search" onSubmit={event => { event.preventDefault(); setPage(1); setFilters(previous => ({ ...previous, q: draft.trim() })); }}><label className="min-w-0 flex-1 text-sm"><span className="sr-only">按岗位名称查找全部报告</span><input className="field" type="search" maxLength={200} value={draft} onChange={event => setDraft(event.target.value)} placeholder="按岗位名称查找报告" /></label><button className="btn" disabled={loading}>查找</button>{(filters.q || filters.jobId) && <button className="btn-quiet" type="button" onClick={() => { setDraft(""); setFilters({ q: "", jobId: "" }); setPage(1); }}>清除筛选</button>}</form>
    <details className="text-slate-600"><summary className="disclosure">历史资料范围</summary><label className="flex min-h-11 items-center gap-3"><input type="checkbox" checked={includeAudit} onChange={event => { setIncludeAudit(event.target.checked); setPage(1); }} />包含历史核验资料（非真实岗位）</label><p>只影响本人的列表与默认入口；已授权的固定报告仍可通过原链接打开。规则分析报告不会因分析方式而被排除。</p></details>
    {filters.jobId && <p role="status" className="text-sm text-slate-700">正在查看同一岗位的历史报告；各份报告保留生成时固定的材料版本。</p>}
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {loading && <p role="status" className="text-sm text-slate-600">正在加载报告…</p>}
    {!loading && !error && data?.items.length === 0 && <div className="panel space-y-3 text-sm text-slate-600"><p>{filters.q || filters.jobId ? "没有符合条件的报告，可以修改或清除筛选。" : "还没有匹配报告。选择岗位，用已上传的材料生成报告，再决定是否投递。"}</p><Link className="btn-secondary" href="/jobs">去选择岗位 →</Link></div>}
    <div className={data?.items.length ? "workspace-sheet workspace-list" : undefined} aria-busy={loading}>{data?.items.map((report,index) => <ReportHistoryCard report={report} key={report.id} onSameJob={!filters.jobId&&data.items.findIndex(r=>r.jobId===report.jobId)===index ? jobId => { setDraft(""); setFilters({ q: "", jobId }); setPage(1); } : undefined} />)}</div>
    {data && <ListPagination label="报告分页" value={data} busy={loading} onPage={setPage} />}
  </div>;
}
