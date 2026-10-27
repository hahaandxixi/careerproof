"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS, type JobSummary, type Page } from "@/lib/api/domain";
import { CAREER_DIRECTIONS, CAREER_LANGUAGES, EMPTY_DISCOVERY, discoveryHref, directionLabel, readDiscoveryQuery, type DiscoveryQuery } from "@/lib/job-discovery";
import CareerDirectionIcon from "./CareerDirectionIcon";
import { ErrorNotice } from "./AccessGate";
import { useAuth } from "./AuthProvider";

export default function JobDiscovery({ compact = false }: { compact?: boolean }) {
  const { user, status } = useAuth();
  const search = useSearchParams();
  const query = useMemo(() => {
    const value = readDiscoveryQuery(new URLSearchParams(search.toString()));
    return compact ? { ...value, page: 1 } : value;
  }, [search, compact]);
  const [draft, setDraft] = useState({ q: query.q, city: query.city });
  const [data, setData] = useState<Page<JobSummary> | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => { setDraft({ q: query.q, city: query.city }); }, [query.q, query.city]);
  useEffect(() => {
    let current = true;
    // Keep the previous result surface mounted while only its query changes.
    setBusy(true); setError("");
    api.listJobs({ ...query, pageSize: compact ? 3 : 12 }).then(value => {
      if (!current) return;
      setData(value);
      if (!compact && value.page !== query.page) window.history.replaceState(null, "", discoveryHref({ ...query, page: value.page }));
    }).catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setBusy(false); });
    return () => { current = false; };
  }, [query, compact, revision]);
  const direction = CAREER_DIRECTIONS.find(item => item.id === query.direction);
  function choose(patch: Partial<DiscoveryQuery>) {
    const next = { ...query, q: draft.q.trim().slice(0, 200), city: draft.city.trim().slice(0, 100), page: 1, ...patch };
    const href = discoveryHref(next);
    // Next 15 synchronizes native History updates with useSearchParams. This is
    // a same-page client filter, not a server navigation or a new scroll target.
    window.history.pushState(null, "", compact ? href.replace(/^\/jobs/, "/") : href);
  }
  const reset = () => { setDraft({ q: "", city: "" }); choose({ ...EMPTY_DISCOVERY }); };
  const moreHref = discoveryHref({ ...query, page: 1 });
  const Heading = compact ? "h2" : "h1";
  return <section aria-labelledby="technical-jobs-title" className={`min-w-0 space-y-4 ${compact ? "rounded-2xl bg-indigo-50/40 p-3 sm:p-5" : ""}`} id="technical-jobs">
    <div className="flex flex-wrap items-start justify-between gap-3"><div>
      {!compact && <p className="text-xs font-semibold tracking-wide text-indigo-600">职业与岗位探索</p>}
      <Heading id="technical-jobs-title" className={compact ? "mt-1 text-2xl font-bold tracking-tight" : "mt-1 text-3xl font-bold tracking-tight sm:text-4xl"}>{compact ? "探索技术岗位" : "发现适合你的技术岗位"}</Heading>
      <p className="mt-2 text-sm leading-6 text-slate-500">先找感兴趣的岗位，再用材料核对每项要求。</p>
    </div>{compact ? <Link className="inline-flex min-h-11 items-center text-sm font-medium text-indigo-700 underline" href={moreHref}>查看全部岗位 →</Link> : status === "authenticated" && user?.role === "student" ? <Link className="btn-secondary shrink-0" href="/recommendations">按我的材料推荐岗位 →</Link> : null}</div>
    <form id="job-discovery-search" role="search" aria-label="岗位搜索" className="flex min-w-0 items-center gap-2 rounded-xl border border-indigo-300 bg-white p-1.5 shadow-sm focus-within:ring-2 focus-within:ring-indigo-100" onSubmit={event => { event.preventDefault(); choose({}); }}>
      <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="ml-2 h-5 w-5 shrink-0 text-indigo-500"><circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4 4"/></svg>
      <label htmlFor="job-discovery-keyword" className="sr-only">关键词</label>
      <input id="job-discovery-keyword" type="search" className="min-h-12 min-w-0 flex-1 rounded-md bg-transparent px-1 text-base text-slate-900 outline-none placeholder:text-sm placeholder:text-slate-400" value={draft.q} maxLength={200} placeholder="搜索岗位名称或技术关键词" onChange={event => setDraft({ ...draft, q: event.target.value })}/>
      <button type="submit" className="btn min-h-12 shrink-0 whitespace-nowrap px-4 sm:px-7">搜索岗位</button>
    </form>
    <div className="grid min-w-0 gap-4 lg:grid-cols-[12rem_minmax(0,1fr)]">
      <nav aria-label="技术职业方向" className="career-directions lg:flex-col lg:gap-1 lg:self-start lg:border-r lg:border-slate-200 lg:pr-3">
        <button type="button" aria-pressed={!query.direction} onClick={() => choose({ direction: "", specialty: "", category: "" })} className={`career-direction lg:min-h-11 lg:rounded-lg lg:py-2 ${!query.direction ? "career-direction-active" : ""}`}><span className="flex h-6 w-6 items-center justify-center rounded-md border border-current text-sm" aria-hidden="true">⊞</span><span>全部岗位</span></button>
        {CAREER_DIRECTIONS.map(item => <button key={item.id} type="button" aria-pressed={query.direction === item.id} onClick={() => choose({ direction: item.id, specialty: "", category: "" })} className={`career-direction lg:min-h-11 lg:rounded-lg lg:py-2 ${query.direction === item.id ? "career-direction-active" : ""}`}><CareerDirectionIcon direction={item.id}/><span>{item.label}</span></button>)}
      </nav>
      <div className="min-w-0 space-y-3" aria-busy={busy}>
        <div className="border-b border-slate-200 pb-3">
          {direction && <div className="scrollbar-quiet mb-3 flex gap-2 overflow-x-auto pb-1" role="group" aria-label={`${direction.label}的具体岗位`}>
            <button className={`career-specialty ${!query.specialty ? "career-specialty-active" : ""}`} type="button" aria-pressed={!query.specialty} onClick={() => choose({ specialty: "" })}>全部{direction.label}</button>
            {direction.specialties.map(item => <button key={item.id} type="button" className={`career-specialty ${query.specialty === item.id ? "career-specialty-active" : ""}`} aria-pressed={query.specialty === item.id} onClick={() => choose({ specialty: item.id })}>{item.label}</button>)}
          </div>}
          <div className="grid min-w-0 grid-cols-2 items-end gap-3 sm:grid-cols-[repeat(3,minmax(0,1fr))_auto]">
            <label className="form-label min-w-0 space-y-1">城市<input form="job-discovery-search" className="field !bg-slate-50 !py-2" value={draft.city} maxLength={100} placeholder="全部城市" onChange={event => setDraft({ ...draft, city: event.target.value })}/></label>
            <label className="form-label min-w-0 space-y-1">工作类型<select form="job-discovery-search" className="field !bg-slate-50 !py-2" value={query.employmentType} onChange={event => choose({ employmentType: event.target.value })}><option value="">全部类型</option>{Object.entries(EMPLOYMENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="form-label min-w-0 space-y-1">技术语言<select form="job-discovery-search" className="field !bg-slate-50 !py-2" value={query.language} onChange={event => choose({ language: event.target.value })}><option value="">不限语言</option>{CAREER_LANGUAGES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
            <button type="button" className="inline-flex min-h-10 items-center justify-center whitespace-nowrap rounded-lg px-2 text-sm text-slate-500 underline hover:text-indigo-700" onClick={reset}>重置筛选</button>
          </div>
          {!!query.category && <p className="mt-3 text-xs text-slate-500">旧分类条件：{CATEGORY_LABELS[query.category]} <button type="button" className="ml-2 min-h-11 text-indigo-700 underline" onClick={() => choose({ category: "" })}>清除此条件</button></p>}
        </div>
        <div aria-live="polite" className="flex min-h-8 flex-wrap items-center justify-between gap-2 text-xs leading-5 text-slate-500">
          <p>{busy ? data ? "正在更新筛选，暂时保留上一组结果…" : "正在查找岗位…" : error ? "岗位暂时无法读取" : data ? `共 ${data.total} 个符合条件的岗位` : ""}</p>{!compact && <span>按最近创建排序 · 合成岗位单独标注</span>}
        </div>
        {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)}/>}
        {busy && !data && <div aria-label="岗位加载占位" className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map(i => <div key={i} className="h-44 rounded-2xl border border-slate-200 bg-white p-4"><div className="h-4 w-2/3 rounded bg-slate-100"/><div className="mt-4 h-3 w-1/2 rounded bg-slate-100"/><div className="mt-7 h-8 rounded bg-slate-50"/></div>)}</div>}
        {!error && data?.items.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center"><h2 className="font-semibold">{busy ? "上一组筛选暂无岗位" : "暂时没有符合条件的岗位"}</h2><p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">分类是探索入口，不代表每一类都有已发布岗位。可以换个方向，或清除城市、工作类型和关键词。</p><button type="button" disabled={busy} onClick={reset} className="btn-secondary mt-4 min-h-11">查看全部岗位</button></div>}
        {!error && !!data?.items.length && <div className="grid min-w-0 gap-3 md:grid-cols-2 xl:grid-cols-3">{data.items.map(job => <DiscoveryJobCard key={job.id} job={job} compact={compact}/>)}</div>}
        {!compact && !error && data && data.total > 0 && <nav aria-label="岗位分页" className="flex flex-wrap items-center justify-center gap-3 pt-2 text-sm"><button type="button" className="btn-secondary min-h-11" disabled={busy || data.page <= 1} onClick={() => choose({ page: data.page - 1 })}>上一页</button><span>第 {data.page} / {Math.max(1, Math.ceil(data.total / data.pageSize))} 页</span><button type="button" className="btn-secondary min-h-11" disabled={busy || data.page * data.pageSize >= data.total} onClick={() => choose({ page: data.page + 1 })}>下一页</button></nav>}
      </div>
    </div>
    {!compact && <p className="text-xs leading-5 text-slate-500">技术方向按岗位标题、明确技能及原分类作导航归类；不是能力认证。未识别方向的旧岗位仍可在“全部岗位”查询。</p>}
  </section>;
}

export function DiscoveryJobCard({ job, compact = false }: { job: JobSummary; compact?: boolean }) {
  const Heading = compact ? "h3" : "h2";
  return <article className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-4 transition-colors hover:border-indigo-300 hover:shadow-sm motion-reduce:transition-none">
    <div className="flex min-w-0 items-start gap-3"><span className={`flex shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 ${compact ? "h-8 w-8" : "h-10 w-10"}`}><CareerDirectionIcon direction={job.careerDirection ?? ""}/></span><div className="min-w-0 flex-1"><Heading className={`min-h-12 line-clamp-2 text-base font-semibold leading-6 text-slate-950`}><Link className="break-words hover:text-indigo-700" href={`/jobs/${job.id}`}>{job.title}</Link></Heading><p className={`mt-1 text-xs leading-5 text-slate-500 ${compact ? "truncate" : "break-words"}`} title={job.companyName}>{job.companyName}</p></div></div>
    <div className={`mt-3 flex flex-wrap items-center text-xs ${compact ? "gap-x-2 gap-y-1 text-slate-500" : "gap-1.5"}`}><span className={compact ? "" : "career-meta"}>{job.city || "城市未填写"}</span>{compact && <span aria-hidden="true">·</span>}<span className={compact ? "" : "career-meta"}>{EMPLOYMENT_LABELS[job.employmentType] ?? job.employmentType}</span>{compact && <span aria-hidden="true">·</span>}<span className={compact ? "" : "career-meta"}>{directionLabel(job.careerDirection) ?? `${CATEGORY_LABELS[job.category] ?? "其他方向"} · 未细分`}</span>{job.isDemo && <span className="rounded-md bg-indigo-50 px-2 py-1 text-indigo-700">合成示例岗位</span>}</div>
    {!!job.technicalTags?.length && <ul aria-label="岗位要求中已列出的技术" className="mt-2 flex flex-wrap gap-1.5">{job.technicalTags.slice(0, 4).map(tag => <li key={tag} className={`rounded-md px-2 text-xs text-slate-500 ${compact ? "bg-slate-50 py-0.5" : "border border-slate-100 py-1"}`}>{tag}</li>)}</ul>}
    {job.description && <p className={`mt-3 min-h-12 line-clamp-2 break-words text-sm leading-6 text-slate-700`}>{job.description}</p>}
    <div className={`mt-auto flex items-center justify-between gap-2 ${compact ? "pt-3" : "flex-wrap pt-4"}`}><span className={compact ? "text-sm font-medium tabular-nums text-slate-700" : "text-xs text-slate-500"}>{compact ? `${job.requirementCount} 项要求` : `岗位要求 ${job.requirementCount} 项`}</span><Link className={`inline-flex min-h-11 shrink-0 items-center justify-center whitespace-nowrap rounded-lg px-3 text-sm font-medium ${compact ? "min-w-28 bg-indigo-600 text-white hover:bg-indigo-700" : "bg-indigo-50 text-indigo-700 hover:bg-indigo-100"}`} href={`/jobs/${job.id}`}>查看要求 →</Link></div>
  </article>;
}
