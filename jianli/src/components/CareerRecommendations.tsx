"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, type ProjectHistory, type ResumeHistory } from "@/lib/api/client";
import {
  CATEGORY_LABELS,
  EMPLOYMENT_LABELS,
  type JobRecommendationResult,
} from "@/lib/api/domain";
import { jobAnalysisHref } from "@/lib/recommendation-selection";
import { ErrorNotice } from "./AccessGate";

const PRIORITY_LABELS = {
  high: "优先了解",
  medium: "值得比较",
  explore: "探索方向",
};

export default function CareerRecommendations() {
  const [resumes, setResumes] = useState<ResumeHistory[]>([]);
  const [projects, setProjects] = useState<ProjectHistory[]>([]);
  const [resumeVersionId, setResumeVersionId] = useState("");
  const [projectVersionIds, setProjectVersionIds] = useState<string[]>([]);
  const [result, setResult] = useState<JobRecommendationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    Promise.all([api.listResumes(), api.listProjects()]).then(([resumeRows, projectRows]) => {
      if (!current) return;
      setResumes(resumeRows); setProjects(projectRows);
      setResumeVersionId(
        resumeRows.flatMap(item => item.versions).find(version => version.status === "completed")?.id ?? "",
      );
      setProjectVersionIds(
        projectRows.flatMap(project => project.versions.filter(version => version.status === "completed").slice(0, 1))
          .slice(0, 10).map(version => version.id),
      );
    }).catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [revision]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!resumeVersionId) return;
    setBusy(true); setError(""); setResult(null);
    try {
      setResult(await api.recommendJobs({ resumeVersionId, projectVersionIds, limit: 5 }));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const availableResumes = resumes.flatMap(resume => resume.versions
    .filter(version => version.status === "completed")
    .map(version => ({ ...version, title: resume.title })));

  return <div className="space-y-6">
    <section>
      <p className="text-sm text-indigo-600">学生职业探索</p>
      <h1 className="mt-1 text-3xl font-bold">根据我的材料推荐职业与岗位</h1>
      <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">系统一次读取所选简历和项目，从当前已发布岗位中寻找有材料证据支撑的方向。推荐顺序只表示材料与岗位要求的贴合程度，不代表能力认证或录用概率。</p>
    </section>

    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    <form className="panel space-y-5" onSubmit={submit}>
      <div><h2 className="text-lg font-semibold">选择材料版本</h2><p className="mt-1 text-sm text-slate-500">默认选择最近完成解析的简历，以及每个项目最近完成的一版。</p></div>
      {loading ? <p className="text-sm text-slate-500">正在加载材料…</p> : <fieldset disabled={busy} className="space-y-4">
        <label className="block text-sm font-medium">简历版本<select className="field mt-2" required value={resumeVersionId} onChange={event => setResumeVersionId(event.target.value)}><option value="">请选择已完成的简历</option>{availableResumes.map(version => <option key={version.id} value={version.id}>{version.title} · 第 {version.versionNumber} 版 · {version.originalFilename} · {version.materialRole === "reference" ? "第三方参考，不计评级" : "个人作品"}</option>)}</select></label>
        {!availableResumes.length && <p className="text-sm text-amber-700">还没有可用简历，请先<Link href="/portfolio" className="underline">上传并完成解析</Link>。</p>}
        <div><p className="text-sm font-medium">项目或作品版本（最多 10 项）</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{projects.map(project => <div key={project.id} className="rounded-lg bg-slate-50 p-3"><p className="text-sm font-medium">{project.name}</p>{project.versions.filter(version => version.status === "completed").map(version => <label key={version.id} className="mt-2 flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={projectVersionIds.includes(version.id)} disabled={!projectVersionIds.includes(version.id) && projectVersionIds.length >= 10} onChange={event => setProjectVersionIds(value => event.target.checked ? [...value, version.id] : value.filter(id => id !== version.id))} /><span>第 {version.versionNumber} 版 · {version.originalFilename} · {version.materialRole === "reference" ? "第三方参考，不计评级" : "个人作品"}</span></label>)}</div>)}</div></div>
        <div className="rounded-xl bg-indigo-50 p-4 text-xs leading-6 text-indigo-900">本步骤只在本地检索已经解析的材料，不调用外部模型、不增加 API 用量。选定岗位后，仍可进入现有 DeepSeek 带引用分析。</div>
        <button className="btn" disabled={!resumeVersionId || busy}>{busy ? "正在检索全部岗位…" : "生成职业推荐"}</button>
      </fieldset>}
    </form>

    {result && <section className="space-y-4">
      <div className="panel"><p className="text-sm text-indigo-600">主要推荐方向</p><h2 className="mt-1 text-2xl font-bold">{result.primaryDirection ? CATEGORY_LABELS[result.primaryDirection] ?? result.primaryDirection : "当前材料不足以确定方向"}</h2><p className="mt-3 text-sm leading-7 text-slate-600">{result.summary}</p></div>
      {!result.recommendations.length && <div className="panel text-sm text-slate-500">当前没有可推荐的已发布岗位。</div>}
      {result.recommendations.map(item => <article className="panel" key={item.jobId}>
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs text-indigo-600">{CATEGORY_LABELS[item.category] ?? item.category} · {EMPLOYMENT_LABELS[item.employmentType] ?? item.employmentType}</p><h3 className="mt-1 text-xl font-semibold">{item.jobTitle}</h3><p className="mt-1 text-sm text-slate-500">{item.companyName} · {item.city}</p></div><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700">{PRIORITY_LABELS[item.priority]}</span></div>
        <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3"><div className="rounded-lg bg-slate-50 p-3"><strong>{item.supportedCount}</strong><p className="mt-1 text-xs text-slate-500">项有项目证据</p></div><div className="rounded-lg bg-slate-50 p-3"><strong>{item.claimedCount}</strong><p className="mt-1 text-xs text-slate-500">项仅见简历声明</p></div><div className="rounded-lg bg-slate-50 p-3"><strong>{item.assessedCount}/{item.requirementCount}</strong><p className="mt-1 text-xs text-slate-500">项可由当前规则比较</p></div></div>
        {!!item.matchedSkills.length && <div className="mt-4"><p className="text-sm font-medium">匹配线索</p><div className="mt-2 flex flex-wrap gap-2">{item.matchedSkills.map(skill => <span key={skill} className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-700">{skill}</span>)}</div></div>}
        {!!item.evidence.length && <details className="mt-4 rounded-xl border border-slate-200 p-3"><summary className="cursor-pointer text-sm font-medium">查看推荐依据</summary><ul className="mt-3 space-y-3">{item.evidence.map((evidence, index) => <li className="text-xs leading-6 text-slate-600" key={`${evidence.filePath}-${index}`}><strong>{evidence.skill}</strong> · {evidence.explanation}<br /><span className="break-all text-slate-400">{evidence.filePath} · 第 {evidence.lineStart}–{evidence.lineEnd} 行</span></li>)}</ul></details>}
        {!!item.gaps.length && <p className="mt-4 text-sm leading-7 text-amber-800"><strong>主要待补：</strong>{item.gaps.join("；")}</p>}
        <Link className="btn mt-5 inline-block" href={jobAnalysisHref(item.jobId, resumeVersionId, projectVersionIds)}>查看岗位并生成完整 AI 报告</Link>
      </article>)}
    </section>}
  </div>;
}
