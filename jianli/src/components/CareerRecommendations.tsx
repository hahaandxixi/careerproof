"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, type ProjectHistory, type ResumeHistory } from "@/lib/api/client";
import {
  CATEGORY_LABELS,
  type CareerPlanResult,
} from "@/lib/api/domain";
import { jobAnalysisHref, resolveInitialMaterialSelection } from "@/lib/recommendation-selection";
import { careerComparisonText, careerPlanConfigurationBlocked, careerPlanDisplayIdentity, careerPlanFailureMessage, careerPlanRecommendations, visibleCareerChanges } from "@/lib/career-plan-display";
import { ErrorNotice } from "./AccessGate";
import { useAuth } from "./AuthProvider";
import ProjectVersionPicker from "./ProjectVersionPicker";
import ResumeVersionPicker from "./ResumeVersionPicker";
import { sourceRelativePath } from "@/lib/source-label";
import CareerRequirementsComparison from "./CareerRequirementsComparison";

const PRIORITY_LABELS = {
  high: "优先了解",
  medium: "值得比较",
  explore: "探索方向",
};
const validationHint = (status: string) => status === "change_attribution_conflict"
  ? "对比只能确认变化同时发生，不能证明补证导致推荐档位变化。"
  : status === "change_fact_conflict"
    ? "这段 AI 说明与已保存的材料或岗位变化冲突，请以下方逐项变化为准。"
    : status === "saved_plan_needs_recheck"
      ? "请核对下方规则候选、逐项变化和可定位引用；历史 AI 建议不会自动恢复。"
      : "这是有限的表述检查；请核对已展示的操作与尚未核验的运行、覆盖范围。";
const EMPTY_PROJECT_IDS: string[] = [];

export default function CareerRecommendations({ initialResumeVersionId = "", initialProjectVersionIds = EMPTY_PROJECT_IDS }: {
  initialResumeVersionId?: string;
  initialProjectVersionIds?: string[];
}) {
  const { user } = useAuth();
  return <CareerPlanWorkspace key={JSON.stringify([user?.id, initialResumeVersionId, initialProjectVersionIds])}
    initialResumeVersionId={initialResumeVersionId} initialProjectVersionIds={initialProjectVersionIds} />;
}

function CareerPlanWorkspace({ initialResumeVersionId, initialProjectVersionIds }: {
  initialResumeVersionId: string;
  initialProjectVersionIds: string[];
}) {
  const [resumes, setResumes] = useState<ResumeHistory[]>([]);
  const [projects, setProjects] = useState<ProjectHistory[]>([]);
  const [resumeVersionId, setResumeVersionId] = useState("");
  const [projectVersionIds, setProjectVersionIds] = useState<string[]>([]);
  const [savedResult, setResult] = useState<CareerPlanResult | null>(null);
  const [resultKind, setResultKind] = useState<"current" | "history">("current");
  const [expandedCandidates, setExpandedCandidates] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [readingCitation, setReadingCitation] = useState("");
  const [fragmentRevision, refreshFragment] = useState(0);
  const [historyRequest, setHistoryRequest] = useState(0);
  const [historyError, setHistoryError] = useState("");
  const [editingMaterials, setEditingMaterials] = useState(false);
  const [historyNotice, setHistoryNotice] = useState("");
  const [externalAiConsent, setExternalAiConsent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errorSource, setErrorSource] = useState<"materials" | "generation">("materials");
  const [selectionNotice, setSelectionNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const [configurationStatus, setConfigurationStatus] = useState("");

  useEffect(() => {
    let current = true;
    setLoading(true); setError(""); setErrorSource("materials"); setSelectionNotice("");
    setConfigurationStatus("");
    Promise.all([api.listResumes(), api.listProjects()]).then(([resumeRows, projectRows]) => {
      if (!current) return;
      setResumes(resumeRows); setProjects(projectRows);
      const selection = resolveInitialMaterialSelection(
        resumeRows.flatMap(row => row.versions).filter(version => version.status === "completed").map(version => version.id),
        projectRows.flatMap(row => row.versions).filter(version => version.status === "completed").map(version => version.id),
        initialResumeVersionId, initialProjectVersionIds,
      );
      setResumeVersionId(selection.resumeVersionId);
      setProjectVersionIds(selection.projectVersionIds);
      if ((initialResumeVersionId && selection.resumeVersionId !== initialResumeVersionId)
        || initialProjectVersionIds.some(id => !selection.projectVersionIds.includes(id))) {
        setSelectionNotice("链接中的部分材料版本不可用或不属于当前账号，请重新选择并核对版本。");
      }
    }).catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [revision, initialResumeVersionId, initialProjectVersionIds]);

  useEffect(() => {
    if (new URLSearchParams(location.search).has("returnPlan")) setHistoryRequest(1);
  }, []);

  useEffect(() => {
    if (!historyRequest) return;
    let current = true;
    setHistoryLoading(true);
    setHistoryError("");
    setHistoryNotice("");
    const returnPlan = new URLSearchParams(location.search).get("returnPlan");
    void (returnPlan && historyRequest === 1 ? api.getCareerPlan(returnPlan) : api.latestCareerPlan()).then(saved => {
      if (!current) return;
      if (saved) {
        const originalPlan = new URLSearchParams(location.search).get("returnPlan");
        if (originalPlan && saved.planId !== originalPlan && historyRequest === 1) {
          setHistoryNotice("原规划不是当前保存的最新规划，无法恢复该引用。");
          return;
        }
        setReadingCitation("");
        setResult(saved);
        setResultKind("history");
        setExpandedCandidates(false);
        setEditingMaterials(false);
      } else {
        setHistoryNotice("暂无保存的职业规划。");
      }
    }).catch(reason => {
      if (current) setHistoryError(errorMessage(reason));
    }).finally(() => {
      if (current) setHistoryLoading(false);
    });
    return () => { current = false; };
  }, [historyRequest]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!resumeVersionId || !externalAiConsent || busy || historyLoading || configurationStatus) return;
    setReadingCitation(""); setBusy(true); setError(""); setErrorSource("generation"); setResult(null); setHistoryNotice(""); setHistoryError("");
    setResultKind("current"); setExpandedCandidates(false);
    try {
      const next = await api.createCareerPlan({ resumeVersionId, projectVersionIds, limit: 10, externalAiConsent });
      setResult(next);
      setEditingMaterials(false);
      if (careerPlanConfigurationBlocked(next.aiStatus)) setConfigurationStatus(next.aiStatus);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function clearDisplayedResult() {
    setReadingCitation(""); setResult(null); setResultKind("current"); setExpandedCandidates(false);
    setHistoryNotice("");
  }

  function viewPreviousPlan() {
    if (busy || historyLoading) return;
    setHistoryRequest(value => value + 1);
  }

  function openEvidence(event: React.MouseEvent<HTMLAnchorElement>, citationId: string) {

    event.preventDefault();
    const hash = `#plan-citation-${citationId}`;
    history.replaceState(null, "", hash);
    if (readingCitation === citationId) document.getElementById(hash.slice(1))?.focus();
    else setReadingCitation(citationId);
  }

  const result = savedResult ? careerPlanDisplayIdentity(savedResult) : null;
  const projectIds = new Set(result?.materials.filter(material => material.kind === "project").map(material => material.id));
  useEffect(() => {
    const changed = () => refreshFragment(value => value + 1);
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    if (!savedResult) return;
    const params = new URLSearchParams(location.search);
    const originalPlan = params.get("returnPlan");
    if (originalPlan && originalPlan !== savedResult.planId) return;
    const hash = location.hash;
    if (!hash.startsWith("#plan-citation-")) {
      if (readingCitation) setReadingCitation("");
      if (!hash.startsWith("#plan-job-")) return;
    }
    let id: string;
    try { id = decodeURIComponent(hash.slice(1)); } catch { return; }
    if (id.startsWith("plan-citation-") && readingCitation !== id.slice("plan-citation-".length)) {
      setReadingCitation(id.slice("plan-citation-".length));
      return;
    }
    const target = document.getElementById(id);
    if (!target) {
      if (!expandedCandidates && savedResult.recommendations.some(job =>
        `plan-job-${job.jobId}` === id ||
        job.evidence.some(evidence => `plan-citation-${evidence.citationId}` === id))) setExpandedCandidates(true);
      return;
    }
    for (let parent = target.parentElement; parent; parent = parent.parentElement) {
      if (parent instanceof HTMLDetailsElement) parent.open = true;
    }
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "start" });
  }, [savedResult, expandedCandidates, readingCitation, fragmentRevision]);
  const visibleRecommendations = result ? careerPlanRecommendations(result, expandedCandidates) : [];
  const visibleChanges = result ? visibleCareerChanges(result.changes, visibleRecommendations) : [];
  const tiers = (["high", "medium", "explore", null] as const).map(priority => ({
    priority,
    jobs: visibleRecommendations.filter(item => priority ? item.priority === priority : !Object.hasOwn(PRIORITY_LABELS, item.priority)),
  })).filter(tier => tier.jobs.length);

  const comparisonJobs = tiers.flatMap(tier => tier.jobs);
  const hasComparisonJobs = comparisonJobs.length > 1;
  const comparison = result && !result.aiFallbackUsed && result.aiPlan?.comparison;

  const materialForm = <div id="career-material-selection">
    <div className="career-selection-head">
      <h2 className="text-lg font-semibold">选择材料版本</h2>
      {result && <button type="button" className="btn-secondary btn-compact" aria-expanded={editingMaterials} aria-controls="career-material-form" onClick={() => setEditingMaterials(value => !value)}>{editingMaterials ? "收起材料选择" : "更换材料"}</button>}
    </div>
    <form id="career-material-form" className="panel space-y-4" hidden={Boolean(result) && !editingMaterials} onSubmit={submit}>
      <p className="text-sm text-slate-600">一份简历、最多 10 份作品。参考材料不计入个人评级。</p>
      {loading ? <p className="text-sm text-slate-500">正在加载材料…</p> : <fieldset disabled={busy || historyLoading} className="space-y-4">
        <ResumeVersionPicker resumes={resumes} selectedId={resumeVersionId} onChange={id => { setResumeVersionId(id); clearDisplayedResult(); }} />
        <ProjectVersionPicker projects={projects} selectedIds={projectVersionIds} onChange={ids => { setProjectVersionIds(ids); clearDisplayedResult(); }} />
        <label className="flex items-start gap-3 rounded-xl bg-brand-surface p-3 text-sm leading-6 text-brand-ink"><input type="checkbox" className="mt-1" checked={externalAiConsent} onChange={event => setExternalAiConsent(event.target.checked)} /><span>同意将规则筛出的最多 3 个岗位要求、缺口和每岗最多 3 条必要证据片段发送给当前配置的模型。模型不可用时仅显示规则候选；结果仅保存在我的账号中。</span></label>
        <button className="btn" disabled={!resumeVersionId || !externalAiConsent || busy || historyLoading || !!configurationStatus}>{busy ? "正在生成 AI 职业规划…" : configurationStatus ? "当前 AI 配置不可用" : "生成 AI 职业规划"}</button>
        {configurationStatus && <p role="status" className="text-sm text-amber-800">{careerPlanFailureMessage(configurationStatus)}</p>}
      </fieldset>}
    </form>
    </div>;

  return <div className="space-y-6">
    <h1 className="text-3xl font-bold">职业与岗位推荐</h1>

    {error && <ErrorNotice message={error}
      retryLabel={errorSource === "generation" ? "保留材料，返回重试" : "重新加载材料"}
      retry={() => {
        if (errorSource === "materials") setRevision(value => value + 1);
        else setError("");
      }} />}
    {historyError && <ErrorNotice message={historyError} retryLabel="重新读取历史规划" retry={viewPreviousPlan} />}
    {selectionNotice && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{selectionNotice}</p>}
    {materialForm}
    {result && <section className="space-y-4" data-plan-id={result.planId ?? undefined}>
      <header className="panel space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm text-slate-600">{resultKind === "history" ? "上次保存的规划" : result.planId ? "本次规划" : "本次候选岗位（未保存）"}</p>
            <h2 className="text-2xl font-semibold">{result.primaryDirection ? CATEGORY_LABELS[result.primaryDirection] ?? result.primaryDirection : "当前材料不足以确定方向"}</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {resultKind === "history" && <button type="button" className="btn-quiet btn-compact" onClick={clearDisplayedResult}>收起历史结果</button>}
          </div>
        </div>
      </header>
      {result.aiFallbackUsed ? <section className="panel space-y-3 text-sm text-amber-800"><p>{careerPlanFailureMessage(result.aiStatus)}</p>{!result.planId && <p className="text-xs">本次未保存职业规划，上次保存的规划保持不变。</p>}{!!result.aiValidationIssues?.length && <details className="space-y-2"><summary className="cursor-pointer font-medium">查看原因</summary>{result.aiValidationIssues.map((issue, index) => <div key={index} className="space-y-2 rounded-lg border border-amber-200 p-3"><p>{issue.reason}</p><blockquote className="border-l-2 border-amber-300 pl-3">被拒绝的表述：{issue.rejectedClaim}</blockquote><div>{issue.citationIds.map(id => <a key={id} className="mr-3 underline" href={`#plan-citation-${id}`} onClick={event => openEvidence(event, id)}>核对引用 {id}</a>)}</div><p className="text-xs">{validationHint(result.aiStatus)}</p></div>)}</details>}</section> : null}
      {!result.recommendations.length && <div className="panel text-sm text-slate-500">当前没有可推荐的已发布岗位。</div>}
      {tiers.map(({priority, jobs}) => <section className="career-tier" data-priority={priority ?? undefined} key={priority ?? "other"}>
        <h3 className="text-base font-semibold">{priority ? PRIORITY_LABELS[priority] : "推荐岗位"}</h3>
        <div className="career-tier-jobs">
          {jobs.map(item => {
            const activeEvidence = readingCitation ? item.evidence.filter(evidence => evidence.citationId === readingCitation) : [];
            const matchedSkills = hasComparisonJobs
              ? item.matchedSkills.filter(skill => !item.requirements?.some(requirement => requirement.skill.trim() === skill.trim()))
              : item.matchedSkills;
            return <article id={`plan-job-${item.jobId}`} tabIndex={-1} className="career-job-card scroll-mt-24" key={item.jobId}>
              <div className="min-w-0 space-y-2">
                <div>
                  <h4 className="break-words text-lg font-semibold">{item.jobTitle}</h4>
                  {item.companyName && <p className="break-words text-sm text-slate-600">{item.companyName}</p>}
                </div>
                {!!matchedSkills.length && <ul className="career-skill-list" aria-label="匹配技能">{matchedSkills.map(skill => <li key={skill}>{skill}</li>)}</ul>}
              </div>
              <Link className={priority === "high" ? "btn shrink-0" : "btn-secondary shrink-0"} href={jobAnalysisHref(item.jobId, result.materials.find(material => material.kind === "resume")?.id ?? resumeVersionId, result.materials.filter(material => material.kind === "project").map(material => material.id))}>查看岗位</Link>
              {!!activeEvidence.length && <ul className="space-y-3 border-t border-slate-100 pt-3">{activeEvidence.map((evidence, index) => <li tabIndex={-1} id={evidence.citationId ? `plan-citation-${evidence.citationId}` : undefined} className="scroll-mt-24 text-xs leading-6 text-slate-600" key={`${evidence.filePath}-${index}`}><strong>{evidence.citationId ? `${evidence.citationId} · ` : ""}{evidence.skill}</strong> · {evidence.explanation}<br /><span className="break-all text-slate-400">{sourceRelativePath({ filePath: evidence.filePath, projectVersionId: evidence.projectVersionId && projectIds.has(evidence.projectVersionId) ? evidence.projectVersionId : undefined })} · 第 {evidence.lineStart}–{evidence.lineEnd} 行</span>{evidence.snippet && <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded bg-white p-2 text-slate-700">{evidence.snippet}</pre>}{evidence.projectFileId && evidence.projectVersionId && <Link className="mt-2 inline-block text-brand-hover underline" href={`/materials/project/${evidence.projectVersionId}?fileId=${evidence.projectFileId}&lineStart=${evidence.lineStart}&lineEnd=${evidence.lineEnd}&from=recommendations&planCitation=${encodeURIComponent(evidence.citationId ?? "")}&planId=${encodeURIComponent(result.planId ?? "")}`}>打开原始文件并定位行号</Link>}</li>)}</ul>}
            </article>;
        })}
        </div>
      </section>)}
      {result.recommendations.length > careerPlanRecommendations(result, false).length && <button type="button" className="rounded-xl border border-slate-200 px-4 py-3 text-sm text-brand-hover" aria-expanded={expandedCandidates} onClick={() => setExpandedCandidates(value => !value)}>{expandedCandidates ? "收起其他候选，只看重点岗位" : `展开其余 ${result.recommendations.length - visibleRecommendations.length} 个规则候选`}</button>}

      {(hasComparisonJobs || comparison) && <section className="career-saved-advice" aria-label="岗位方向比较">
        <h3 className="text-lg font-semibold">岗位方向比较</h3>
        {hasComparisonJobs && <CareerRequirementsComparison key={result.planId} jobs={comparisonJobs} />}
        {comparison && <details className="career-comparison-original">
          <summary className="disclosure">完整比较说明</summary>
          <p className="career-reason max-w-[90ch]">{careerComparisonText(comparison, result.recommendations)}</p>
        </details>}
      </section>}

      {!!result.previousPlanId && visibleChanges.length > 0 && <details className="panel"><summary className="cursor-pointer font-semibold">查看这些岗位与上次规划的变化</summary><p className="mt-1 text-xs text-slate-500">分别核对材料版本、岗位基本信息、岗位要求、可定位证据和规则档位；同时变化不证明因果或能力提升。</p><ul className="mt-3 space-y-2">{visibleChanges.map(change => <li key={change.jobId} className="rounded-lg bg-slate-50 p-3 text-sm"><strong>{change.jobTitle}</strong>{change.status === "not_in_current" && <span className="ml-2 rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800">本轮列表未见</span>}<p className="mt-1 text-slate-600">{change.detail}</p>{change.jobDetailsChanged && <p className="mt-1 text-amber-800">岗位基本信息已变，请与材料变化分开核对。</p>}{change.requirementsChanged && <p className="mt-1 text-amber-800">岗位要求已变，本次档位不能归因于补证。</p>}{change.evidenceIds.map(id => <a key={id} href={`#plan-citation-${id}`} onClick={event => openEvidence(event, id)} className="mr-3 text-xs text-brand-primary underline">查看新证据 {id}</a>)}</li>)}</ul></details>}
    </section>}
    {!result && <div className="flex flex-wrap items-center gap-3 text-sm">
      <button type="button" className="btn-secondary" disabled={busy || loading || historyLoading} onClick={viewPreviousPlan}>{historyLoading ? "正在读取上次规划…" : "查看上次保存的规划"}</button>
      {historyNotice && <p role="status" className="text-slate-600">{historyNotice}</p>}
    </div>}
  </div>;
}
