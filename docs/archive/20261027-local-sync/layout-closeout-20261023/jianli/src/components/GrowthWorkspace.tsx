"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { materialSelectionChanged } from "@/lib/material-upload";
import { GrowthMaterialReview } from "./GrowthUploadReturn";
import { api, errorMessage, type ResumeHistory, type ProjectHistory } from "@/lib/api/client";
import type { GrowthTask, JobSummary } from "@/lib/api/domain";
import { createGrowthRequestGuard, growthCanSelect, growthAutoQueryStep, growthTargetJobState, growthJobListQuery, growthJobPageBounds, growthSaveMaterialsPayload, GROWTH_STATUS } from "@/lib/growth-workflow";
import { useAuth } from "./AuthProvider";
import ResumeVersionPicker from "./ResumeVersionPicker";
import ProjectVersionPicker from "./ProjectVersionPicker";
import GrowthComparison from "./GrowthComparison";
import EnterpriseReplyContext from "./EnterpriseReplyContext";
import PrivateAnswerDraft from "./PrivateAnswerDraft";
import ListPagination from "./ListPagination";
import EvidenceLink from "./EvidenceLink";
import { growthNextAction } from "@/lib/growth-next-action";
import type { Page } from "@/lib/api/domain";

export default function GrowthWorkspace({ id }: { id?: string }) {
  const { user } = useAuth();
  return <GrowthContent key={`${user?.id}:${id}`} id={id} />;
}

function GrowthContent({ id }: { id?: string }) {
  const guard = useRef(createGrowthRequestGuard()).current;
  // 公开岗位列表与私有任务读写使用独立 guard：列表读取不得废弃保存/分析回执，
  // 任务操作也不得让列表 busy 卡死；两 guard 都只在刷新/隐藏/换身份时整体清除。
  const jobGuard = useRef(createGrowthRequestGuard()).current;
  const [task, setTask] = useState<GrowthTask | null>(null);
  const [tasks, setTasks] = useState<GrowthTask[]>([]);
  const [taskPage, setTaskPage] = useState(1);
  const [taskData, setTaskData] = useState<(Page<GrowthTask> & { unavailableCount: number }) | null>(null);
  const [resumes, setResumes] = useState<ResumeHistory[]>([]);
  const [projects, setProjects] = useState<ProjectHistory[]>([]);
  const [resumeId, setResumeId] = useState("");
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [targetJobId, setTargetJobId] = useState("");
  const [jobPickerOpen, setJobPickerOpen] = useState(false);
  const [jobQuery, setJobQuery] = useState("");
  const [jobPage, setJobPage] = useState(1);
  const [jobItems, setJobItems] = useState<JobSummary[]>([]);
  const [jobTotal, setJobTotal] = useState(0);
  const [jobPageSize, setJobPageSize] = useState(10);
  const [jobBusy, setJobBusy] = useState(false);
  const [jobError, setJobError] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pageHidden, setPageHidden] = useState(false);
  const [revision, setRevision] = useState(0);
  const polls = useRef(0);
  const locked = useRef(false);
  useEffect(() => {
    const ticket = guard.start(); jobGuard.clear();
    // 当前身份/任务由外层key隔离；同任务恢复读取不卸载私人草稿，避免丢失本机编辑。
    setTasks([]); setTaskData(null); setError(""); setBusy(true);
    setJobItems([]); setJobTotal(0); setJobPickerOpen(false); setJobBusy(false); setJobError("");
    polls.current = 0;
    const load = id ? Promise.all([api.growthTask(id), api.listResumes(), api.listProjects()]).then(([value, r, p]) => {
      if (!guard.accepts(ticket)) return;
      setTask(value); setResumes(r); setProjects(p);
      const materials = value.materials.length ? value.materials : value.baseMaterials;
      setResumeId(materials.find(m => m.kind === "resume")?.id || "");
      setProjectIds(materials.filter(m => m.kind === "project").map(m => m.id));
      setTargetJobId(value.targetJobId || "");
    }) : api.listGrowthTasks(taskPage, 20).then(value => { if (guard.accepts(ticket)) { if (value.page !== taskPage) setTaskPage(value.page); else { setTasks(value.items); setTaskData(value); } } });
    void load.catch(reason => { if (guard.accepts(ticket)) setError(errorMessage(reason)); }).finally(() => { if (guard.accepts(ticket)) setBusy(false); });
    const visibility = () => {
      if (document.visibilityState === "hidden") {
        setPageHidden(true);
        guard.clear(); jobGuard.clear(); setTaskData(null);
        setTasks([]); setResumes([]); setProjects([]); setResumeId(""); setProjectIds([]); setTargetJobId(""); setJobItems([]); setJobTotal(0); setJobPickerOpen(false); setJobBusy(false); setJobError(""); setConsent(false); setBusy(false);
      } else { setPageHidden(false); setRevision(v => v + 1); }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => { guard.clear(); jobGuard.clear(); document.removeEventListener("visibilitychange", visibility); };
  }, [id, revision, guard, jobGuard, taskPage]);

  useEffect(() => {
    if (!id || !task) return;
    const plan = growthAutoQueryStep({ polls: polls.current, analyzing: task.status === "analyzing", busy, error });
    if (plan.notice !== null) setNotice(plan.notice);
    if (!plan.poll) return;
    const timer = setTimeout(() => {
      const ticket = guard.start(); ++polls.current;
      void api.growthTask(id).then(value => { if (guard.accepts(ticket)) setTask(value); }).catch(reason => {
        if (guard.accepts(ticket)) { setTask(null); setError(errorMessage(reason)); }
      });
    }, 1500);
    return () => clearTimeout(timer);
  }, [id, task, busy, error, guard]);

  async function perform(operation: () => Promise<GrowthTask>, onSaved?: (value: GrowthTask) => void) {
    if (locked.current) return;
    locked.current = true;
    const ticket = guard.start(); setBusy(true); setError(""); setNotice("");
    try { const value = await operation(); if (guard.accepts(ticket)) { setTask(value); setConsent(false); polls.current = 0; onSaved?.(value); } }
    catch (reason) { if (guard.accepts(ticket)) { setTask(null); setError(errorMessage(reason)); } }
    finally { locked.current = false; if (guard.accepts(ticket)) setBusy(false); }
  }

  async function loadJobList(query: string, page: number) {
    const ticket = jobGuard.start(); setJobBusy(true); setJobError("");
    try {
      const list = await api.listJobs(growthJobListQuery(query, page));
      if (jobGuard.accepts(ticket)) { setJobItems(list.items); setJobTotal(list.total); setJobPageSize(list.pageSize); setJobPage(page); setJobQuery(query); }
    } catch (reason) { if (jobGuard.accepts(ticket)) setJobError(errorMessage(reason)); }
    finally { if (jobGuard.accepts(ticket)) setJobBusy(false); }
  }
  return <div className="layout-closeout space-y-6" hidden={pageHidden}>
    <div><Link className="text-sm text-indigo-700 underline" href="/reports">← 我的报告</Link><h1 className="mt-3 text-2xl font-bold">{id ? "从缺口到新证据" : "我的补证任务"}</h1><p className="mt-2 text-sm leading-6 text-slate-600">上传与分析是行动进度，不等于能力认证；企业原投递保持固定。</p></div>
    <button className="btn-secondary" disabled={busy} onClick={() => { setConsent(false); setRevision(v => v + 1); }}>刷新任务状态</button>
    {busy && <p role="status">正在处理…</p>}{error && <p role="alert" className="text-sm text-rose-700">{error}</p>}{notice && <p role="status" className="text-sm text-amber-800">{notice}</p>}
    {!id && !busy && !error && (tasks.length ? <ul className="space-y-3">{tasks.map(value => <li key={value.id} className="panel"><Link className="font-medium text-indigo-700 underline" href={`/growth/${value.id}`}>{value.requirementTitle}</Link><p className="mt-2 text-sm">{value.jobTitle}{value.targetJobId && value.targetJobId !== value.jobId ? ` → 已保存目标：${value.targetJobTitle || value.targetJobId}` : ""} · {GROWTH_STATUS[value.status]}</p><p className="mt-1 text-sm text-slate-600">{value.plan.deliverable}</p></li>)}</ul> : taskData?.total === 0 ? <p className="panel">暂无补证任务。从报告中选一条缺口，先完成一个小目标。<Link className="mt-3 block text-indigo-700 underline" href="/reports">从我的报告开始 →</Link></p> : null)}
    {!id && taskData && <>{taskData.unavailableCount > 0 && <p role="status" className="text-sm text-amber-800">本页有 {taskData.unavailableCount} 条已保存任务暂时无法读取，仍计入总数；可重试读取或翻页查看其他任务，不代表任务已删除。</p>}<ListPagination label="补证任务分页" value={taskData} busy={busy} onPage={setTaskPage} /></>}
    {task && (() => {
      const jobState = growthTargetJobState(task, targetJobId);
      const materialsChanged = materialSelectionChanged(task.materials, resumeId, projectIds);
      const next = growthNextAction(task, materialsChanged || jobState.selectionChanged);
      const jobBounds = growthJobPageBounds(jobTotal, jobPage, jobPageSize);
      return <>
      <section className="surface-muted space-y-3 rounded-xl p-4" aria-label="当前任务与下一步">
        <p className="text-xs text-slate-600">{task.jobTitle}</p><h2 className="text-lg font-semibold leading-7">{task.requirementTitle}</h2>
        <p role="status" className="text-sm font-medium text-indigo-800">{GROWTH_STATUS[task.status]}</p>
        <EvidenceLink targetId={next.target} className="btn">{next.label} →</EvidenceLink>
        {task.targetReportId && <Link className="ml-4 inline-flex min-h-11 items-center text-sm text-indigo-700 underline" href={`/reports/${task.targetReportId}`}>打开新报告 / 继续补证</Link>}
        <p className="text-xs leading-6 text-slate-600">任务进度不代表能力认证；原报告和企业已收到的投递保持固定。</p>
      </section>
      {task.comparison && <div id="growth-result" className="scroll-mt-32"><details className="panel"><summary className="cursor-pointer font-semibold">查看本次逐项变化 · {task.comparison.items.length} 项要求 · 待人工核验</summary><div className="mt-4"><GrowthComparison task={task} /></div></details></div>}
      {task.enterpriseReply && <EnterpriseReplyContext context={task.enterpriseReply} />}
      {task.enterpriseReply && task.comparison && <Link className="text-sm text-indigo-700 underline" href={`#growth-requirement-${task.requirementId}`}>查看这项问题对应的新版报告变化解释 →</Link>}
      {task.actionNeedsRecheck && <p role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm leading-6 text-amber-900">这条任务固定了旧版 AI 建议，但当前校验发现它包含需要重新核对的内容。请先核对基准引用和自己填写的交付计划；不要仅按旧建议重复上传同一材料。{task.taskPlanWarning && ` ${task.taskPlanWarning}`}</p>}
      <section className="panel space-y-3"><h2 className="text-lg font-semibold">1. 固定基准与交付要求</h2><p>{task.jobTitle} · {task.requirementTitle}</p>{jobState.crossJob && <p className="text-sm">已保存目标岗位：<span className="font-medium">{jobState.savedTargetJobTitle}</span>（与任务原岗位不同；企业问题与基准引用仍关联原岗位要求）</p>}<p className="text-sm text-indigo-700">{GROWTH_STATUS[task.status]}</p><p className="font-medium">交付物：{task.plan.deliverable}</p><details className="border-t border-slate-200 pt-2"><summary className="cursor-pointer py-2 text-sm text-indigo-700">展开原始缺口、建议与核验步骤</summary><div className="space-y-3 pt-2"><p className="text-sm leading-6">原始缺口：{task.gap || "原报告未记录具体缺口，请人工核对。"}</p><p className="text-sm leading-6">原报告建议{task.actionSource === "ai_suggestion" ? "（AI 证据建议）" : task.actionSource === "review" ? "（人工复核后提示）" : task.actionSource === "rules" ? "（本地规则提示）" : ""}：{task.originalAction || "暂无"}</p>{task.actionSource === "ai_suggestion" && !!task.actionCitationIds?.length && <div className="flex flex-wrap gap-3 text-sm">{task.actionCitationIds.map(citation => <Link key={citation} className="text-indigo-700 underline" href={`/reports/${task.baseReportId}#citation-${citation}`}>核对基准引用 {citation}</Link>)}</div>}<p className="text-sm">执行步骤</p><ol className="list-decimal space-y-1 pl-5 text-sm">{task.plan.steps.map((s, i) => <li key={i}>{s}</li>)}</ol><p className="text-sm">核验条件</p><ul className="list-disc space-y-1 pl-5 text-sm">{task.plan.acceptanceChecks.map((s, i) => <li key={i}>{s}</li>)}</ul></div></details><Link className="text-sm text-indigo-700 underline" href={`/reports/${task.baseReportId}#requirement-${task.requirementId}`}>打开原报告该要求</Link><p className="text-xs leading-6 text-slate-500">此处基准已固定；原报告后来复核不改写它。整份报告重新分析，下面会逐项展示变化。</p></section>
      <section id="growth-materials" className="panel scroll-mt-32 space-y-4"><h2 className="text-lg font-semibold">{growthCanSelect(task) ? "2. 上传并关联明确的材料版本" : "2. 本轮材料（已固定）"}</h2>
        {growthCanSelect(task) ? <><p className="text-sm leading-6 text-slate-600">前往材料中心，给原项目上传具名新版或新增运行/贡献材料；解析完成后回到任务并读取。只改文件名但内容相同不能作为补证变化。</p><Link className="text-indigo-700 underline" href={`/portfolio?growthTask=${task.id}`}>前往上传新版材料 →</Link></> : <div className="space-y-2 text-sm leading-6">
          <p role="status">本轮材料已固定，不能在这个任务中重新关联或覆盖。{task.targetReportId ? "如需继续补证，请从新报告选择下一条缺口；原任务和已投递报告保持不变。" : "请先查看下方处理记录；结果保存后可从新报告继续。"}</p>
          <p>已保存目标岗位：{jobState.savedTargetJobTitle}</p>
          {task.targetReportId && <Link className="inline-flex min-h-11 items-center text-indigo-700 underline" href={`/reports/${task.targetReportId}`}>从新报告选择下一条缺口 →</Link>}
        </div>}
        {growthCanSelect(task) && <fieldset disabled={busy} className="space-y-4"><div className="space-y-2 rounded-xl border border-indigo-200 p-3"><p className="text-sm font-medium">目标岗位（默认任务原岗位；分析开始后与材料同时锁定）</p><p className="text-xs leading-6 text-slate-600">已保存目标：{jobState.savedTargetJobTitle}{jobState.crossJob ? "（≠ 任务原岗位）" : "（= 任务原岗位）"}。生成新报告只使用已保存目标；改选岗位必须重新保存材料选择才会生效。</p><details open={jobPickerOpen} onToggle={event => { const open = (event.target as HTMLDetailsElement).open; setJobPickerOpen(open); if (open && !jobItems.length && !jobBusy) void loadJobList(jobQuery, 1); }}><summary className="cursor-pointer text-sm text-indigo-700 underline">选择已发布的新岗位（公开列表，可搜索/翻页）</summary><div className="mt-2 space-y-2"><form className="flex gap-2" onSubmit={event => { event.preventDefault(); void loadJobList(jobQuery, 1); }}><input className="field flex-1" value={jobQuery} onChange={event => setJobQuery(event.target.value)} placeholder="按标题或公司搜索已发布岗位" aria-label="搜索已发布岗位" /><button className="btn-secondary" type="submit" disabled={jobBusy}>搜索</button></form>{jobError && <p role="alert" className="text-sm text-rose-700">{jobError}</p>}{jobBusy && <p role="status" className="text-sm">正在读取公开岗位列表…</p>}<ul className="space-y-1">{jobItems.map(job => <li key={job.id} className="text-sm"><label className="flex items-start gap-2"><input type="radio" name="growth-target-job" className="mt-1" checked={targetJobId === job.id} onChange={() => setTargetJobId(job.id)} /><span className="min-w-0 flex-1">{job.title} · {job.companyName}{job.id === task.jobId && <span className="ml-1 text-xs text-slate-500">（任务原岗位）</span>}{job.id === jobState.savedTargetJobId && job.id !== task.jobId && <span className="ml-1 text-xs text-emerald-700">（已保存目标）</span>}</span></label></li>)}</ul>{jobItems.length === 0 && !jobBusy && !jobError && <p className="text-xs text-slate-600">没有匹配的已发布岗位。</p>}<div className="flex items-center gap-3 text-xs text-slate-600"><span>共 {jobTotal} 个已发布岗位 · 第 {jobPage} 页</span><button type="button" className="btn-secondary" disabled={jobBusy || !jobBounds.hasPrevious} onClick={() => void loadJobList(jobQuery, jobPage - 1)}>上一页</button><button type="button" className="btn-secondary" disabled={jobBusy || !jobBounds.hasNext} onClick={() => void loadJobList(jobQuery, jobPage + 1)}>下一页</button></div></div></details>{targetJobId && targetJobId !== jobState.savedTargetJobId && <button type="button" className="text-sm text-indigo-700 underline" onClick={() => setTargetJobId("")}>清除本次改选，恢复已保存目标岗位</button>}</div><Suspense fallback={<><ResumeVersionPicker resumes={resumes} selectedId={resumeId} onChange={setResumeId} /><ProjectVersionPicker projects={projects} selectedIds={projectIds} onChange={setProjectIds} /></>}><GrowthMaterialReview resumes={resumes} projects={projects} resumeId={resumeId} projectIds={projectIds} onResumeChange={setResumeId} onProjectsChange={setProjectIds} /></Suspense><div className="surface-muted space-y-2 p-3 text-sm leading-6"><p className="font-medium">当前选择：{resumeId ? "1 份简历" : "未选简历"} · {projectIds.length} 个项目版本</p><p role="status">{materialsChanged ? "当前选择尚未保存。请核对上方版本后，点击“保存本次材料选择”；上传成功不会自动关联。" : "当前选择与已保存记录一致。"}</p>{task.materials.length > 0 && materialsChanged && <p>生成报告仍使用下方已保存版本，不使用尚未保存的改选。</p>}</div><button id="growth-save" className="btn-secondary scroll-mt-32" disabled={!resumeId} onClick={() => void perform(() => api.growthMaterials(task.id, growthSaveMaterialsPayload(task, targetJobId, { resumeVersionId: resumeId, projectVersionIds: projectIds })), value => setTargetJobId(value.targetJobId || ""))}>保存本次材料选择</button></fieldset>}{growthCanSelect(task) && jobState.selectionChanged && <p role="status" className="text-sm leading-6 text-amber-800">已改选目标岗位但尚未保存：本次改选不会生效，生成新报告仍使用已保存目标「{jobState.savedTargetJobTitle}」；请重新点击“保存本次材料选择”。</p>}<p className="text-sm font-medium">服务端已保存材料 · {task.materials.length} 项</p>{!task.materials.length && <p className="text-sm text-slate-600">尚未保存本轮材料；先在上方选择并确认保存。</p>}<ul className="space-y-1 text-xs leading-6 text-slate-600">{task.materials.map(m => <li key={`${m.kind}:${m.id}`} className="break-all">已保存：{m.title} · 第{m.versionNumber}版 · {m.materialRole === "reference" ? "第三方参考，不计评级" : m.kind === "resume" ? "简历" : "个人作品"}<details className="mt-1"><summary className="cursor-pointer text-indigo-700">查看校验信息</summary><p className="break-all">版本 {m.id} · 摘要 {m.contentHash}</p></details></li>)}</ul></section>
      {task.materials.length > 0 && !task.analysisTaskId && <section id="growth-analysis" className="panel scroll-mt-32 space-y-4"><h2 className="text-lg font-semibold">3. 生成新报告</h2><p className="text-sm leading-6 text-slate-600">使用已保存版本和已保存目标岗位「{jobState.savedTargetJobTitle}」的当前要求，生成本人私有报告，不自动更新或再次投递给企业。AI解释需要单独确认；未授权时仅依据本地规则生成，不外发材料。{jobState.selectionChanged && ` 已改选的目标岗位尚未保存，本次生成不会使用它。`}{materialsChanged && " 当前材料改选尚未保存，本次生成仍使用已保存版本。"}</p><label className="flex items-start gap-2 text-sm leading-6"><input className="mt-1" type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)} /><span>我同意将本次岗位要求、规则结论和脱敏后的必要证据片段发送给 DeepSeek 官方 API 生成带引用解释；不主动加入账号身份、完整简历或原始文件。自由文本脱敏可能遗漏未标记信息，请先核对材料。</span></label><button className="btn" disabled={busy} onClick={() => void perform(() => api.analyzeGrowth(task.id, consent))}>生成新报告</button></section>}
      {task.analysisTaskId && <section id="growth-processing" className="panel scroll-mt-32 space-y-3"><p className="text-sm">{task.analysisError || (task.targetReportId ? "新报告已保存，可核对变化。" : "材料选择已固定，可读取处理记录和结果。")}</p><Link className="text-sm text-indigo-700 underline" href={`/tasks/${task.analysisTaskId}`}>查看处理记录</Link>{task.targetReportId && <Link className="ml-4 text-sm text-indigo-700 underline" href={`/reports/${task.targetReportId}`}>打开新报告</Link>}</section>}
      <PrivateAnswerDraft taskId={task.id} requirementId={task.requirementId} requirementTitle={task.requirementTitle} jobTitle={task.jobTitle} baseReportId={task.baseReportId} targetReportId={task.targetReportId} crossJob={jobState.crossJob} />
      <p className="text-xs leading-6 text-slate-500">{task.boundary}</p>
    </>;
    })()}
  </div>;
}
