"use client";

import { demoJobAlias, displayJobTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS, type Page, type JobSummary } from "@/lib/api/domain";
import { ErrorNotice } from "./AccessGate";
import JobDiscovery from "./JobDiscovery";
import ListPagination from "./ListPagination";

const EMPTY_FILTER = { q: "", category: "", city: "", employmentType: "" };
export function ManagedJobCard({ job, changing, onStatusChange }: {
  job: JobSummary; changing: string; onStatusChange(job: JobSummary): void;
}) {
  const alias = demoJobAlias(job.id);
  return <article className="workspace-row grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
    <div className="min-w-0 space-y-2">
    <div className="flex items-start justify-between gap-3"><div className="min-w-0"><Link className="break-words text-lg font-semibold hover:text-indigo-600" href={`/jobs/${job.id}`}>{displayJobTitle(job.title, job.id)}</Link><p className="mt-1 text-sm text-slate-600">{alias?.companyName ?? job.companyName} · {job.city || "城市未填写"} · {EMPLOYMENT_LABELS[job.employmentType] ?? job.employmentType}</p></div><span className="status-chip">{({ draft: "草稿", published: "已发布", closed: "已关闭" } as Record<string, string>)[job.status] ?? job.status}</span></div>
    <p className="line-clamp-3 text-sm leading-6 text-slate-600">{(alias?.description ?? job.description) || "暂无描述"}</p>
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600"><span>{CATEGORY_LABELS[job.category] ?? job.category} · {job.requirementCount} 项要求</span>{job.applicationCount != null && <span>投递 {job.applicationCount} · 待回复 {job.pendingApplicationCount ?? 0}</span>}</div>
    </div>
    <div className="card-actions lg:max-w-[26rem] lg:justify-end">
      <Link className={job.status === "draft" ? "btn" : "btn-secondary"} href={`/jobs/${job.id}/edit`}>编辑岗位</Link>
      <Link className={job.status === "draft" ? "btn-secondary" : "btn"} href={`/jobs/${job.id}/applications`}>查看投递</Link>
      <button type="button" className={job.status === "published" ? "btn-danger-quiet ml-auto" : "btn-secondary ml-auto"} disabled={!!changing} onClick={() => {
        if (job.status === "published" && !window.confirm("关闭此岗位？关闭后将停止接收新投递，已有投递和固定报告仍会保留。")) return;
        onStatusChange(job);
      }}>{changing === job.id ? "更新中…" : job.status === "published" ? "关闭岗位" : "发布岗位"}</button>
    </div>
  </article>;
}
export default function JobList({ mine = false, initialQuery = "" }: { mine?: boolean; initialQuery?: string }) {
  return mine ? <ManagedJobList initialQuery={initialQuery}/> : <JobDiscovery/>;
}
function ManagedJobList({ initialQuery }: { initialQuery: string }) {
  const mine = true;
  const [draft, setDraft] = useState({ ...EMPTY_FILTER, q: initialQuery });
  const [filter, setFilter] = useState({ ...EMPTY_FILTER, q: initialQuery });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<JobSummary> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [changing, setChanging] = useState("");
  useEffect(() => {
    let current = true;
    setBusy(true); setError("");
    api.listJobs({ ...filter, page, pageSize: 12 }, mine).then(value => { if (current) { setData(value); if (value.page !== page) setPage(value.page); } })
      .catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setBusy(false); });
    return () => { current = false; };
  }, [filter, page, mine, revision]);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  async function changeStatus(job: JobSummary) {
    setChanging(job.id); setError("");
    try { await api.updateJob(job.id, { status: job.status === "published" ? "closed" : "published" }); refresh(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setChanging(""); }
  }
  return <div className="space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="page-title mt-1">{mine ? "我的岗位" : "岗位发现"}</h1></div>{mine ? <Link className="btn" href="/jobs/new">发布新岗位</Link> : <Link className="btn-secondary" href="/recommendations">按材料推荐职业</Link>}</div>
    <form className="panel grid gap-3 sm:grid-cols-2 lg:grid-cols-5" onSubmit={event => { event.preventDefault(); setPage(1); setFilter({ ...draft }); }}>
      <label className="space-y-1 text-sm">关键词<input className="field" value={draft.q} maxLength={200} placeholder="岗位、企业或描述" onChange={e => setDraft({ ...draft, q: e.target.value })} /></label>
      <label className="space-y-1 text-sm">方向<select className="field" value={draft.category} onChange={e => setDraft({ ...draft, category: e.target.value })}><option value="">全部方向</option>{Object.entries(CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="space-y-1 text-sm">城市<input className="field" value={draft.city} maxLength={100} placeholder="如：杭州" onChange={e => setDraft({ ...draft, city: e.target.value })} /></label>
      <label className="space-y-1 text-sm">工作类型<select className="field" value={draft.employmentType} onChange={e => setDraft({ ...draft, employmentType: e.target.value })}><option value="">全部类型</option>{Object.entries(EMPLOYMENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="flex items-end gap-2"><button className="btn" disabled={busy}>筛选</button><button className="btn-secondary" type="button" onClick={() => { setDraft(EMPTY_FILTER); setFilter(EMPTY_FILTER); setPage(1); }}>重置</button></div>
    </form>
    {error && <ErrorNotice message={error} retry={refresh} />}
    {busy && <p role="status" className="text-sm text-slate-500">正在加载岗位…</p>}
    {!busy && !error && data?.items.length === 0 && <div className="panel space-y-3"><h2 className="section-title">{Object.values(filter).some(Boolean) ? "没有符合筛选的岗位" : "暂无岗位"}</h2>{Object.values(filter).some(Boolean) ? <button type="button" className="btn-secondary" onClick={() => { setDraft(EMPTY_FILTER); setFilter(EMPTY_FILTER); setPage(1); }}>清除筛选</button> : <Link className="btn" href="/jobs/new">创建第一个岗位</Link>}</div>}
    {!error && <div className={data?.items.length ? "workspace-sheet workspace-list" : undefined}>{data?.items.map(job => <ManagedJobCard key={job.id} job={job} changing={changing} onStatusChange={job => void changeStatus(job)}/>)}</div>}
    {data && <ListPagination label="岗位分页" value={data} busy={busy} onPage={setPage}/>}
  </div>;
}
