"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS, type JobSummary, type Page } from "@/lib/api/domain";
import { CAREER_DIRECTIONS, CAREER_LANGUAGES, EMPTY_DISCOVERY, discoveryHref, directionLabel, readDiscoveryQuery, type DiscoveryQuery } from "@/lib/job-discovery";
import CareerDirectionIcon from "./CareerDirectionIcon";
import { ErrorNotice } from "./AccessGate";

export default function JobDiscovery({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
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
    setBusy(true); setError(""); setData(null);
    api.listJobs({ ...query, pageSize: compact ? 3 : 12 }).then(value => {
      if (!current) return;
      setData(value);
      if (!compact && value.page !== query.page) router.replace(discoveryHref({ ...query, page: value.page }), { scroll: false });
    }).catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setBusy(false); });
    return () => { current = false; };
  }, [query, compact, revision, router]);
  const direction = CAREER_DIRECTIONS.find(item => item.id === query.direction);
  function choose(patch: Partial<DiscoveryQuery>) {
    const next = { ...query, q: draft.q.trim().slice(0, 200), city: draft.city.trim().slice(0, 100), page: 1, ...patch };
    const href = discoveryHref(next);
    if (compact) router.replace(href.replace(/^\/jobs/, "/"), { scroll: false });
    else router.push(href, { scroll: false });
  }
  const reset = () => { setDraft({ q: "", city: "" }); choose({ ...EMPTY_DISCOVERY }); };
  const moreHref = discoveryHref({ ...query, page: 1 });
  const Heading = compact ? "h2" : "h1";
  return <section aria-labelledby="technical-jobs-title" className="min-w-0 space-y-4" id="technical-jobs">
    <div className="flex flex-wrap items-start justify-between gap-3"><div>
      <p className="text-xs font-semibold tracking-wide text-indigo-600">{compact ? "从方向开始探索" : "职业与岗位探索"}</p>
      <Heading id="technical-jobs-title" className={compact ? "mt-1 text-2xl font-bold tracking-tight" : "mt-1 text-3xl font-bold tracking-tight sm:text-4xl"}>{compact ? "探索技术岗位" : "发现适合你的技术岗位"}</Heading>
      <p className="mt-2 text-sm leading-6 text-slate-500">选择技术方向，查看岗位要求，再用你的材料核对证据。</p>
    </div>{compact ? <Link className="inline-flex min-h-11 items-center text-sm font-medium text-indigo-700 underline" href={moreHref}>查看全部岗位 →</Link> : <Link className="btn-secondary shrink-0" href="/recommendations">按材料推荐职业 →</Link>}</div>
    <div className={compact ? "min-w-0 space-y-3" : "grid min-w-0 gap-4 lg:grid-cols-[12rem_minmax(0,1fr)]"}>
      <nav aria-label="技术职业方向" className={compact ? "career-directions" : "career-directions lg:flex-col lg:rounded-2xl lg:border lg:border-slate-200 lg:bg-white lg:p-2"}>
        <button type="button" aria-pressed={!query.direction} onClick={() => choose({ direction: "", specialty: "", category: "" })} className={`career-direction ${!query.direction ? "career-direction-active" : ""}`}><span className="flex h-6 w-6 items-center justify-center rounded-md border border-current text-sm" aria-hidden="true">⊞</span><span>全部岗位</span></button>
        {CAREER_DIRECTIONS.map(item => <button key={item.id} type="button" aria-pressed={query.direction === item.id} onClick={() => choose({ direction: item.id, specialty: "", category: "" })} className={`career-direction ${query.direction === item.id ? "career-direction-active" : ""}`}><CareerDirectionIcon direction={item.id}/><span>{item.label}</span></button>)}
      </nav>
      <div className="min-w-0 space-y-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-3 sm:p-4">
          {direction && <div className="mb-3 flex gap-2 overflow-x-auto pb-1" role="group" aria-label={`${direction.label}的具体岗位`}>
            <button className={`career-specialty ${!query.specialty ? "career-specialty-active" : ""}`} type="button" aria-pressed={!query.specialty} onClick={() => choose({ specialty: "" })}>全部{direction.label}</button>
            {direction.specialties.map(item => <button key={item.id} type="button" className={`career-specialty ${query.specialty === item.id ? "career-specialty-active" : ""}`} aria-pressed={query.specialty === item.id} onClick={() => choose({ specialty: item.id })}>{item.label}</button>)}
          </div>}
          <form className="grid min-w-0 grid-cols-2 gap-3 xl:grid-cols-[minmax(6rem,.8fr)_minmax(7rem,.8fr)_minmax(7rem,.8fr)_minmax(9rem,1.5fr)_auto]" onSubmit={event => { event.preventDefault(); choose({}); }}>
            <label className="min-w-0 space-y-1 text-xs text-slate-500">城市<input className="field" value={draft.city} maxLength={100} placeholder="全部城市" onChange={event => setDraft({ ...draft, city: event.target.value })}/></label>
            <label className="min-w-0 space-y-1 text-xs text-slate-500">工作类型<select className="field" value={query.employmentType} onChange={event => choose({ employmentType: event.target.value })}><option value="">全部类型</option>{Object.entries(EMPLOYMENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="min-w-0 space-y-1 text-xs text-slate-500">技术语言<select className="field" value={query.language} onChange={event => choose({ language: event.target.value })}><option value="">不限语言</option>{CAREER_LANGUAGES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
            <label className="min-w-0 space-y-1 text-xs text-slate-500">关键词<input className="field" value={draft.q} maxLength={200} placeholder="岗位、企业或关键词" onChange={event => setDraft({ ...draft, q: event.target.value })}/></label>
            <div className="col-span-2 flex items-end gap-2 xl:col-span-1"><button type="submit" className="btn min-h-11 whitespace-nowrap">搜索</button><button type="button" className="inline-flex min-h-11 items-center whitespace-nowrap px-2 text-sm text-slate-500 underline hover:text-indigo-700" onClick={reset}>重置</button></div>
          </form>
          {!!query.category && <p className="mt-3 text-xs text-slate-500">旧分类条件：{CATEGORY_LABELS[query.category]} <button type="button" className="ml-2 min-h-11 text-indigo-700 underline" onClick={() => choose({ category: "" })}>清除此条件</button></p>}
        </div>
        <div aria-live="polite" className="flex min-h-8 flex-wrap items-center justify-between gap-2 text-xs leading-5 text-slate-500">
          <p>{busy ? "正在查找岗位…" : error ? "岗位暂时无法读取" : data ? `共 ${data.total} 个符合条件的岗位${compact && data.total ? ` · 首页展示 ${data.items.length} 个` : ""}` : ""}</p><span>按最近创建排序 · 合成岗位单独标注</span>
        </div>
        {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)}/>}
        {busy && <div aria-label="岗位加载占位" className={`grid gap-3 ${compact ? "md:grid-cols-3" : "md:grid-cols-2 xl:grid-cols-3"}`}>{[0, 1, 2].map(i => <div key={i} className="h-44 rounded-2xl border border-slate-200 bg-white p-4"><div className="h-4 w-2/3 rounded bg-slate-100"/><div className="mt-4 h-3 w-1/2 rounded bg-slate-100"/><div className="mt-7 h-8 rounded bg-slate-50"/></div>)}</div>}
        {!busy && !error && data?.items.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center"><h2 className="font-semibold">暂时没有符合条件的岗位</h2><p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">分类是探索入口，不代表每一类都有已发布岗位。可以换个方向，或清除城市、工作类型和关键词。</p><button type="button" onClick={reset} className="btn-secondary mt-4 min-h-11">查看全部岗位</button></div>}
        {!busy && !error && !!data?.items.length && <div className={`grid min-w-0 gap-3 ${compact ? "md:grid-cols-3" : "md:grid-cols-2 xl:grid-cols-3"}`}>{data.items.map(job => <DiscoveryJobCard key={job.id} job={job} compact={compact}/>)}</div>}
        {!compact && !busy && !error && data && data.total > 0 && <nav aria-label="岗位分页" className="flex flex-wrap items-center justify-center gap-3 pt-2 text-sm"><button type="button" className="btn-secondary min-h-11" disabled={data.page <= 1} onClick={() => choose({ page: data.page - 1 })}>上一页</button><span>第 {data.page} / {Math.max(1, Math.ceil(data.total / data.pageSize))} 页</span><button type="button" className="btn-secondary min-h-11" disabled={data.page * data.pageSize >= data.total} onClick={() => choose({ page: data.page + 1 })}>下一页</button></nav>}
      </div>
    </div>
    <p className="text-xs leading-5 text-slate-500">技术方向按岗位标题、明确技能及原分类作导航归类；不是能力认证。未识别方向的旧岗位仍可在“全部岗位”查询。</p>
  </section>;
}

export function DiscoveryJobCard({ job, compact = false }: { job: JobSummary; compact?: boolean }) {
  const Heading = compact ? "h3" : "h2";
  return <article className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-4 transition-colors hover:border-indigo-200">
    <div className="flex min-w-0 items-start gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600"><CareerDirectionIcon direction={job.careerDirection ?? ""}/></span><div className="min-w-0 flex-1"><Heading className="text-base font-semibold leading-6 text-slate-950"><Link className="break-words hover:text-indigo-700" href={`/jobs/${job.id}`}>{job.title}</Link></Heading><p className="mt-1 break-words text-xs leading-5 text-slate-500">{job.companyName}</p></div></div>
    <div className="mt-3 flex flex-wrap gap-1.5 text-xs"><span className="career-meta">{job.city || "城市未填写"}</span><span className="career-meta">{EMPLOYMENT_LABELS[job.employmentType] ?? job.employmentType}</span><span className="career-meta">{directionLabel(job.careerDirection) ?? `${CATEGORY_LABELS[job.category] ?? "其他方向"} · 未细分`}</span>{job.isDemo && <span className="rounded-md bg-indigo-50 px-2 py-1 text-indigo-700">合成示例岗位</span>}</div>
    {!!job.technicalTags?.length && <ul aria-label="岗位要求中已列出的技术" className="mt-2 flex flex-wrap gap-1.5">{job.technicalTags.slice(0, 4).map(tag => <li key={tag} className="rounded-md border border-slate-100 px-2 py-1 text-xs text-slate-500">{tag}</li>)}</ul>}
    {job.description && <p className="mt-3 line-clamp-2 break-words text-xs leading-5 text-slate-500">{job.description}</p>}
    <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-4"><span className="text-xs text-slate-500">岗位要求 {job.requirementCount} 项</span><Link className="inline-flex min-h-11 items-center rounded-lg bg-indigo-50 px-3 text-sm font-medium text-indigo-700 hover:bg-indigo-100" href={`/jobs/${job.id}`}>查看要求 →</Link></div>
  </article>;
}
