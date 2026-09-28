"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, type ProjectHistory, type ResumeHistory } from "@/lib/api/client";
import {
  CATEGORY_LABELS,
  EMPLOYMENT_LABELS,
  type CareerPlanResult,
} from "@/lib/api/domain";
import { jobAnalysisHref } from "@/lib/recommendation-selection";
import { careerPlanRecommendations } from "@/lib/career-plan-display";
import { ErrorNotice } from "./AccessGate";
import ProjectVersionPicker from "./ProjectVersionPicker";

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
  const [result, setResult] = useState<CareerPlanResult | null>(null);
  const [resultKind, setResultKind] = useState<"current" | "history">("current");
  const [expandedCandidates, setExpandedCandidates] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyNotice, setHistoryNotice] = useState("");
  const [externalAiConsent, setExternalAiConsent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let current = true;
    setLoading(true); setError(""); setResult(null); setHistoryNotice("");
    Promise.all([api.listResumes(), api.listProjects()]).then(([resumeRows, projectRows]) => {
      if (!current) return;
      setResumes(resumeRows); setProjects(projectRows);
      setResumeVersionId(
        resumeRows.flatMap(item => item.versions).find(version => version.status === "completed")?.id ?? "",
      );
      setProjectVersionIds(
        projectRows.flatMap(project => project.versions.filter(version =>
          version.status === "completed" && version.materialRole !== "reference",
        ).slice(0, 1)).slice(0, 1).map(version => version.id),
      );
    }).catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [revision]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!resumeVersionId || !externalAiConsent || busy || historyLoading) return;
    setBusy(true); setError(""); setResult(null); setHistoryNotice("");
    setResultKind("current"); setExpandedCandidates(false);
    try {
      setResult(await api.createCareerPlan({ resumeVersionId, projectVersionIds, limit: 10, externalAiConsent }));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function clearDisplayedResult() {
    setResult(null); setResultKind("current"); setExpandedCandidates(false);
    setHistoryNotice("");
  }

  async function viewPreviousPlan() {
    if (busy || historyLoading) return;
    setHistoryLoading(true); setError(""); setHistoryNotice("");
    try {
      const saved = await api.latestCareerPlan();
      if (saved) {
        setResult(saved); setResultKind("history"); setExpandedCandidates(false);
      } else {
        setHistoryNotice("暂无保存的职业规划，请先选择材料并生成。");
      }
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setHistoryLoading(false);
    }
  }

  const availableResumes = resumes.flatMap(resume => resume.versions
    .filter(version => version.status === "completed")
    .map(version => ({ ...version, title: resume.title })));
  const visibleRecommendations = result ? careerPlanRecommendations(result, expandedCandidates) : [];
  const visibleJobIds = new Set(visibleRecommendations.map(item => item.jobId));

  return <div className="space-y-6">
    <section>
      <p className="text-sm text-indigo-600">学生职业探索</p>
      <h1 className="mt-1 text-3xl font-bold">根据我的材料推荐职业与岗位</h1>
      <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">系统先用本地证据规则筛出岗位，再由 AI 优先比较不同职业方向的候选岗位、指出缺口和下一份可提交材料。上传新版本后再次生成，可查看证据变化。推荐顺序不代表能力认证或录用概率。</p>
    </section>

    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    <form className="panel space-y-5" onSubmit={submit}>
      <div><h2 className="text-lg font-semibold">选择材料版本</h2><p className="mt-1 text-sm text-slate-500">默认选择最近完成解析的简历和一份个人项目；可勾选最多 10 份作品。第三方参考材料不会计入个人评级。</p></div>
      {loading ? <p className="text-sm text-slate-500">正在加载材料…</p> : <fieldset disabled={busy || historyLoading} className="space-y-4">
        <label className="block text-sm font-medium">简历版本<select className="field mt-2" required value={resumeVersionId} onChange={event => { setResumeVersionId(event.target.value); clearDisplayedResult(); }}><option value="">请选择已完成的简历</option>{availableResumes.map(version => <option key={version.id} value={version.id}>{version.title} · 第 {version.versionNumber} 版 · {version.originalFilename} · {version.materialRole === "reference" ? "第三方参考，不计评级" : "个人作品"}</option>)}</select></label>
        {!availableResumes.length && <p className="text-sm text-amber-700">还没有可用简历，请先<Link href="/portfolio" className="underline">上传并完成解析</Link>。</p>}
        <ProjectVersionPicker projects={projects} selectedIds={projectVersionIds} onChange={ids => { setProjectVersionIds(ids); clearDisplayedResult(); }} />
        <label className="flex items-start gap-3 rounded-xl bg-indigo-50 p-4 text-xs leading-6 text-indigo-900"><input type="checkbox" className="mt-1" checked={externalAiConsent} onChange={event => setExternalAiConsent(event.target.checked)} /><span>同意将规则筛出的最多 3 个岗位要求、缺口和每岗最多 3 条必要证据片段发送给当前配置的模型。模型不可用时仅显示规则候选；结果仅保存在我的账号中。</span></label>
        <button className="btn" disabled={!resumeVersionId || !externalAiConsent || busy || historyLoading}>{busy ? "正在生成 AI 职业规划…" : "生成 AI 职业规划"}</button>
      </fieldset>}
    </form>

    <div className="flex flex-wrap items-center gap-3 text-sm">
      <button type="button" className="text-indigo-700 underline disabled:text-slate-400" disabled={busy || loading || historyLoading} onClick={viewPreviousPlan}>{historyLoading ? "正在读取上次规划…" : "查看上次保存的规划"}</button>
      <span className="text-xs text-slate-500">仅查看，不会调用 AI；不会替换当前选择的材料。</span>
    </div>
    {historyNotice && <p role="status" className="text-sm text-slate-500">{historyNotice}</p>}
    {!result && !loading && !busy && <p role="status" className="panel text-sm text-slate-500">选择材料并生成后，这里只展示本次结果。调整材料后，请重新生成；旧规划保留在账号中。</p>}

    {result && <section className="space-y-4">
      <div className="panel"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm text-indigo-600">{resultKind === "history" ? "上次保存的规划 · 历史结果" : "本次生成的规划"}</p>{resultKind === "history" && <button type="button" className="text-xs text-indigo-700 underline" onClick={clearDisplayedResult}>收起历史结果</button>}</div>{resultKind === "history" && <p className="mt-2 text-xs text-amber-800">这是上次保存材料的结果，不是当前材料的新分析。下方依据以该规划保存的版本为准。</p>}<p className="mt-3 text-xs text-slate-500">主要推荐方向</p><h2 className="mt-1 text-2xl font-bold">{result.primaryDirection ? CATEGORY_LABELS[result.primaryDirection] ?? result.primaryDirection : "当前材料不足以确定方向"}</h2><p className="mt-3 text-sm leading-7 text-slate-600">{result.summary}</p><p className="mt-2 text-xs text-slate-500">结果依据：{result.materials.map(material => `${material.title} 第 ${material.versionNumber} 版`).join("；")}</p></div>
      {result.aiPlan ? <section className="panel space-y-3"><p className="text-sm text-indigo-600">AI 候选岗位比较 · {result.aiModel}</p><h2 className="text-lg font-semibold">值得优先补证的方向</h2><p className="text-sm leading-7 text-slate-700">{result.aiPlan.comparison}</p><div className="flex flex-wrap gap-3">{result.aiPlan.advice.map(advice => <a key={advice.jobId} className="text-xs text-indigo-700 underline" href={`#plan-job-${advice.jobId}`}>{result.recommendations.find(item => item.jobId === advice.jobId)?.jobTitle ?? "查看候选岗位"}</a>)}</div><p className="text-xs text-slate-500">AI 选择的补证重点：{result.recommendations.find(item => item.jobId === result.aiPlan?.focusJobId)?.jobTitle ?? "暂无"}。岗位顺序仍由本地证据规则确定。</p></section> : result.aiFallbackUsed ? <section className="panel space-y-3 text-sm text-amber-800"><p>模型本次未能生成通过校验的规划，已保留候选岗位。</p>{(result.aiValidationIssues ?? []).map((issue, index) => <div key={index} className="space-y-2 rounded-lg border border-amber-200 p-3"><p>{issue.reason}</p><blockquote className="border-l-2 border-amber-300 pl-3">被拒绝的表述：{issue.rejectedClaim}</blockquote><div>{issue.citationIds.map(id => <a key={id} className="mr-3 underline" href={`#plan-citation-${id}`}>核对引用 {id}</a>)}</div><p className="text-xs">这是有限的表述检查；请核对已展示的操作与尚未核验的运行、覆盖范围。</p></div>)}</section> : null}
      {!!result.previousPlanId && result.changes.some(change => visibleJobIds.has(change.jobId)) && <details className="panel"><summary className="cursor-pointer font-semibold">查看这些岗位与上次规划的变化</summary><p className="mt-1 text-xs text-slate-500">只比较保存材料中的可定位证据与规则档位；新增材料不保证提级。</p><ul className="mt-3 space-y-2">{result.changes.filter(change => visibleJobIds.has(change.jobId)).map(change => <li key={change.jobId} className="rounded-lg bg-slate-50 p-3 text-sm"><strong>{change.jobTitle}</strong><p className="mt-1 text-slate-600">{change.detail}</p>{change.evidenceIds.map(id => <a key={id} href={`#plan-citation-${id}`} className="mr-3 text-xs text-indigo-600 underline">查看新证据 {id}</a>)}</li>)}</ul></details>}
      {!result.recommendations.length && <div className="panel text-sm text-slate-500">当前没有可推荐的已发布岗位。</div>}
      {result.recommendations.length > visibleRecommendations.length && <p className="text-sm text-slate-600">仅展示本次重点岗位；其他规则候选已收起，不影响完整结果保存。</p>}
      {visibleRecommendations.map(item => <article id={`plan-job-${item.jobId}`} className="panel scroll-mt-24" key={item.jobId}>
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs text-indigo-600">{CATEGORY_LABELS[item.category] ?? item.category} · {EMPLOYMENT_LABELS[item.employmentType] ?? item.employmentType}</p><h3 className="mt-1 text-xl font-semibold">{item.jobTitle}</h3><p className="mt-1 text-sm text-slate-500">{item.companyName} · {item.city}</p></div><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700">{PRIORITY_LABELS[item.priority]}</span></div>
        <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3"><div className="rounded-lg bg-slate-50 p-3"><strong>{item.supportedCount}</strong><p className="mt-1 text-xs text-slate-500">项有项目证据</p></div><div className="rounded-lg bg-slate-50 p-3"><strong>{item.claimedCount}</strong><p className="mt-1 text-xs text-slate-500">项仅见简历声明</p></div><div className="rounded-lg bg-slate-50 p-3"><strong>{item.assessedCount}/{item.requirementCount}</strong><p className="mt-1 text-xs text-slate-500">项可由当前规则比较</p></div></div>
        {!!item.matchedSkills.length && <div className="mt-4"><p className="text-sm font-medium">匹配线索</p><div className="mt-2 flex flex-wrap gap-2">{item.matchedSkills.map(skill => <span key={skill} className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-700">{skill}</span>)}</div></div>}
        {!!item.evidence.length && <details className="mt-4 rounded-xl border border-slate-200 p-3" open><summary className="cursor-pointer text-sm font-medium">查看推荐依据</summary><ul className="mt-3 space-y-3">{item.evidence.map((evidence, index) => <li id={evidence.citationId ? `plan-citation-${evidence.citationId}` : undefined} className="scroll-mt-24 text-xs leading-6 text-slate-600" key={`${evidence.filePath}-${index}`}><strong>{evidence.citationId ? `${evidence.citationId} · ` : ""}{evidence.skill}</strong> · {evidence.explanation}<br /><span className="break-all text-slate-400">{evidence.filePath} · 第 {evidence.lineStart}–{evidence.lineEnd} 行</span>{evidence.snippet && <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded bg-white p-2 text-slate-700">{evidence.snippet}</pre>}{evidence.projectFileId && evidence.projectVersionId && <Link className="mt-2 inline-block text-indigo-700 underline" href={`/materials/project/${evidence.projectVersionId}?fileId=${evidence.projectFileId}&lineStart=${evidence.lineStart}&lineEnd=${evidence.lineEnd}`}>打开原始文件并定位行号</Link>}</li>)}</ul></details>}
        {!!item.gaps.length && <p className="mt-4 text-sm leading-7 text-amber-800"><strong>主要待补：</strong>{item.gaps.join("；")}</p>}
        {!!item.requirements?.length && <details className="mt-4 rounded-xl border border-slate-200 p-3"><summary className="cursor-pointer text-sm font-medium">查看岗位原文要求与规则覆盖</summary><ul className="mt-2 space-y-2">{item.requirements.map((requirement, index) => <li key={`${requirement.skill}-${index}`} className="text-xs leading-6 text-slate-600"><strong>{requirement.skill}</strong> · {requirement.isRequired ? "必要" : "加分"} · {requirement.weight}/5 · {requirement.ruleVerdict === "unsupported" || requirement.ruleVerdict === "not_evaluated" ? "当前规则无法判断" : requirement.ruleVerdict === "claimed_only" ? "仅见简历声明" : requirement.ruleVerdict === "supported" || requirement.ruleVerdict === "partial" ? "有项目线索" : "待补证据"}<span className="mt-1 block">{requirement.text}</span></li>)}</ul></details>}
        {result.aiPlan?.advice.filter(advice => advice.jobId === item.jobId).map(advice => <div key={advice.jobId} className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50/50 p-4 text-sm leading-7"><strong>AI 补证建议</strong>{item.assessedCount === 0 && <p className="text-xs text-amber-800">该岗位要求尚未进入规则评估范围，以下建议仅供探索，需人工核对材料。</p>}<p>当前判断：{advice.reason}</p><p>关键缺口：{advice.keyGap}</p><p>下一项可提交材料：{advice.nextTask}</p>{advice.taskPlan && <div className="mt-3 space-y-2"><p className="font-medium">提交产物：{advice.taskPlan.deliverable}</p><p>执行步骤</p><ol className="list-decimal pl-5">{advice.taskPlan.steps.map((step, i) => <li key={i}>{step}</li>)}</ol><p>验收时检查</p><ul className="list-disc pl-5">{advice.taskPlan.acceptanceChecks.map((check, i) => <li key={i}>{check}</li>)}</ul><p className="text-xs text-slate-500">这是待完成任务；提交新材料后重新生成规划，核对证据变化。</p></div>}<div>{advice.citationIds.map(id => <a key={id} className="mr-3 text-xs text-indigo-700 underline" href={`#plan-citation-${id}`}>引用 {id}</a>)}</div></div>)}
        <Link className="btn mt-5 inline-block" href={jobAnalysisHref(item.jobId, result.materials.find(material => material.kind === "resume")?.id ?? resumeVersionId, result.materials.filter(material => material.kind === "project").map(material => material.id))}>查看岗位并生成完整 AI 报告</Link>
      </article>)}
      {result.recommendations.length > careerPlanRecommendations(result, false).length && <button type="button" className="rounded-xl border border-slate-200 px-4 py-3 text-sm text-indigo-700" aria-expanded={expandedCandidates} onClick={() => setExpandedCandidates(value => !value)}>{expandedCandidates ? "收起其他候选，只看重点岗位" : `展开其余 ${result.recommendations.length - visibleRecommendations.length} 个规则候选`}</button>}
    </section>}
  </div>;
}
