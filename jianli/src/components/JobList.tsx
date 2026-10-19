"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS, type Page, type JobSummary } from "@/lib/api/domain";
import { ErrorNotice } from "./AccessGate";

const EMPTY_FILTER = { q: "", category: "", city: "", employmentType: "" };
export default function JobList({ mine = false, initialQuery = "" }: { mine?: boolean; initialQuery?: string }) {
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
    api.listJobs({ ...filter, page, pageSize: 12 }, mine).then(value => { if (current) setData(value); })
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
    <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-sm text-indigo-600">{mine ? "企业工作台" : "职业与岗位探索"}</p><h1 className="mt-1 text-3xl font-bold">{mine ? "我的岗位" : "岗位发现"}</h1></div>{mine && <Link className="btn" href="/jobs/new">发布新岗位</Link>}</div>
    {!mine && data?.items.some(job => job.isDemo) && <p className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-600">标有“体验样例”的岗位、企业和配套人物均为虚构，可下载对应材料练习匹配与补证；站内投递仅用于演示，不会发送给BOSS或真实企业。其他岗位由对应企业账号发布。</p>}
    <form className="panel grid gap-3 sm:grid-cols-2 lg:grid-cols-5" onSubmit={event => { event.preventDefault(); setPage(1); setFilter({ ...draft }); }}>
      <label className="space-y-1 text-sm">关键词<input className="field" value={draft.q} maxLength={200} placeholder="岗位、企业或描述" onChange={e => setDraft({ ...draft, q: e.target.value })} /></label>
      <label className="space-y-1 text-sm">方向<select className="field" value={draft.category} onChange={e => setDraft({ ...draft, category: e.target.value })}><option value="">全部方向</option>{Object.entries(CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="space-y-1 text-sm">城市<input className="field" value={draft.city} maxLength={100} placeholder="如：杭州" onChange={e => setDraft({ ...draft, city: e.target.value })} /></label>
      <label className="space-y-1 text-sm">工作类型<select className="field" value={draft.employmentType} onChange={e => setDraft({ ...draft, employmentType: e.target.value })}><option value="">全部类型</option>{Object.entries(EMPLOYMENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="flex items-end gap-2"><button className="btn" disabled={busy}>筛选</button><button className="btn-secondary" type="button" onClick={() => { setDraft(EMPTY_FILTER); setFilter(EMPTY_FILTER); setPage(1); }}>重置</button></div>
    </form>
    {error && <ErrorNotice message={error} retry={refresh} />}
    {busy && <p role="status" className="text-sm text-slate-500">正在加载岗位…</p>}
    {!busy && !error && data?.items.length === 0 && <div className="panel py-10 text-center text-slate-500">{mine ? "你的企业暂未创建岗位。" : "没有符合条件的岗位，试试其他筛选条件。"}{mine ? <Link className="mt-4 block text-indigo-700 underline" href="/jobs/new">创建第一个岗位 →</Link> : <button type="button" className="mt-4 text-indigo-700 underline" onClick={() => { setDraft(EMPTY_FILTER); setFilter(EMPTY_FILTER); setPage(1); }}>清除筛选查看全部岗位</button>}</div>}
    {!error && <div className="grid gap-4 md:grid-cols-2">{data?.items.map(job => <article key={job.id} className="panel">
      <div className="flex items-start justify-between gap-3"><div className="flex flex-wrap items-center gap-2"><Link className="text-lg font-semibold hover:text-indigo-600" href={`/jobs/${job.id}`}>{job.title}</Link>{job.isDemo && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">体验样例 · 虚构企业</span>}</div><span className="text-xs text-slate-500">{EMPLOYMENT_LABELS[job.employmentType] ?? job.employmentType}</span></div>
      <p className="mt-1 text-sm text-slate-500">{job.companyName} · {job.city || "城市未填写"}</p><p className="mt-4 line-clamp-3 text-sm leading-6 text-slate-600">{job.description || "暂无描述"}</p>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2"><span className="rounded bg-indigo-50 px-2 py-1 text-xs text-indigo-700">{CATEGORY_LABELS[job.category] ?? job.category} · {job.requirementCount} 项要求</span><Link href={`/jobs/${job.id}`} className="text-sm text-indigo-600">查看岗位 →</Link></div>
      {mine && <div className="mt-4 flex items-center gap-3 border-t border-slate-100 pt-3 text-sm"><span>{({ draft: "草稿", published: "已发布", closed: "已关闭" } as Record<string, string>)[job.status]}</span><Link className="text-indigo-600" href={`/jobs/${job.id}/edit`}>编辑</Link><button className="text-indigo-600 disabled:opacity-50" disabled={!!changing} onClick={() => void changeStatus(job)}>{changing === job.id ? "更新中…" : job.status === "published" ? "关闭岗位" : "发布岗位"}</button></div>}
    </article>)}</div>}
    {data && data.total > 0 && <div className="flex items-center justify-center gap-4 text-sm"><button className="btn-secondary" disabled={busy || page <= 1} onClick={() => setPage(page - 1)}>上一页</button><span>第 {page} / {Math.max(1, Math.ceil(data.total / data.pageSize))} 页 · 共 {data.total} 个</span><button className="btn-secondary" disabled={busy || page * data.pageSize >= data.total} onClick={() => setPage(page + 1)}>下一页</button></div>}
  </div>;
}
