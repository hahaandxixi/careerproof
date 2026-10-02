"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, type ResumeHistory, type ProjectHistory } from "@/lib/api/client";
import type { GrowthTask } from "@/lib/api/domain";
import { createGrowthRequestGuard, growthCanSelect, GROWTH_STATUS } from "@/lib/growth-workflow";
import { useAuth } from "./AuthProvider";
import ResumeVersionPicker from "./ResumeVersionPicker";
import ProjectVersionPicker from "./ProjectVersionPicker";
import GrowthComparison from "./GrowthComparison";
import EnterpriseReplyContext from "./EnterpriseReplyContext";

export default function GrowthWorkspace({ id }: { id?: string }) {
  const { user } = useAuth();
  return <GrowthContent key={`${user?.id}:${id}`} id={id} />;
}

function GrowthContent({ id }: { id?: string }) {
  const guard = useRef(createGrowthRequestGuard()).current;
  const [task, setTask] = useState<GrowthTask | null>(null);
  const [tasks, setTasks] = useState<GrowthTask[]>([]);
  const [resumes, setResumes] = useState<ResumeHistory[]>([]);
  const [projects, setProjects] = useState<ProjectHistory[]>([]);
  const [resumeId, setResumeId] = useState("");
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const polls = useRef(0);
  const locked = useRef(false);
  useEffect(() => {
    const ticket = guard.start(); setTask(null); setTasks([]); setError(""); setBusy(true);
    polls.current = 0;
    const load = id ? Promise.all([api.growthTask(id), api.listResumes(), api.listProjects()]).then(([value, r, p]) => {
      if (!guard.accepts(ticket)) return;
      setTask(value); setResumes(r); setProjects(p);
      const materials = value.materials.length ? value.materials : value.baseMaterials;
      setResumeId(materials.find(m => m.kind === "resume")?.id || "");
      setProjectIds(materials.filter(m => m.kind === "project").map(m => m.id));
    }) : api.listGrowthTasks().then(value => { if (guard.accepts(ticket)) setTasks(value); });
    void load.catch(reason => { if (guard.accepts(ticket)) setError(errorMessage(reason)); }).finally(() => { if (guard.accepts(ticket)) setBusy(false); });
    const visibility = () => {
      if (document.visibilityState === "hidden") {
        guard.clear(); setTask(null); setTasks([]); setResumes([]); setProjects([]); setResumeId(""); setProjectIds([]); setConsent(false); setBusy(false);
      } else { setRevision(v => v + 1); }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => { guard.clear(); document.removeEventListener("visibilitychange", visibility); };
  }, [id, revision, guard]);

  useEffect(() => {
    if (!id || !task || task.status !== "analyzing" || busy || error) return;
    if (polls.current >= 60) { setNotice("已停止自动查询。任务继续在服务器处理，可点击读取已保存任务；不会新增模型调用。"); return; }
    const timer = setTimeout(() => {
      const ticket = guard.start(); ++polls.current;
      void api.growthTask(id).then(value => { if (guard.accepts(ticket)) setTask(value); }).catch(reason => {
        if (guard.accepts(ticket)) { setTask(null); setError(errorMessage(reason)); }
      });
    }, 1500);
    return () => clearTimeout(timer);
  }, [id, task, busy, error, guard]);

  async function perform(operation: () => Promise<GrowthTask>) {
    if (locked.current) return;
    locked.current = true;
    const ticket = guard.start(); setBusy(true); setError(""); setNotice("");
    try { const value = await operation(); if (guard.accepts(ticket)) { setTask(value); setConsent(false); polls.current = 0; } }
    catch (reason) { if (guard.accepts(ticket)) { setTask(null); setError(errorMessage(reason)); } }
    finally { locked.current = false; if (guard.accepts(ticket)) setBusy(false); }
  }
  return <div className="space-y-6">
    <div><Link className="text-sm text-indigo-700 underline" href="/reports">← 我的报告</Link><h1 className="mt-3 text-2xl font-bold">{id ? "从缺口到新证据" : "我的补证任务"}</h1><p className="mt-2 text-sm leading-6 text-slate-600">上传与分析是行动进度，不等于能力认证；企业原投递保持固定。</p></div>
    <button className="btn-secondary" disabled={busy} onClick={() => { setConsent(false); setRevision(v => v + 1); }}>读取已保存任务</button>
    {busy && <p role="status">正在处理…</p>}{error && <p role="alert" className="text-sm text-rose-700">{error}</p>}{notice && <p role="status" className="text-sm text-amber-800">{notice}</p>}
    {!id && !busy && !error && (tasks.length ? <ul className="space-y-3">{tasks.map(value => <li key={value.id} className="panel"><Link className="font-medium text-indigo-700 underline" href={`/growth/${value.id}`}>{value.requirementTitle}</Link><p className="mt-2 text-sm">{value.jobTitle} · {GROWTH_STATUS[value.status]}</p><p className="mt-1 text-sm text-slate-600">{value.plan.deliverable}</p></li>)}</ul> : <p className="panel">暂无补证任务，请从本人报告的逐项缺口创建。</p>)}
    {task && <>
      {task.enterpriseReply && <EnterpriseReplyContext context={task.enterpriseReply} />}
      {task.enterpriseReply && task.comparison && <Link className="text-sm text-indigo-700 underline" href={`#growth-requirement-${task.requirementId}`}>查看这项问题对应的新版报告变化解释 →</Link>}
      {task.actionNeedsRecheck && <p role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm leading-6 text-amber-900">这条任务固定了旧版 AI 建议，但当前校验发现它包含需要重新核对的内容。请先核对基准引用和自己填写的交付计划；不要仅按旧建议重复上传同一材料。{task.taskPlanWarning && ` ${task.taskPlanWarning}`}</p>}
      <section className="panel space-y-3"><h2 className="text-lg font-semibold">1. 固定基准与交付要求</h2><p>{task.jobTitle} · {task.requirementTitle}</p><p className="text-sm text-indigo-700">{GROWTH_STATUS[task.status]}</p><p className="text-sm leading-6">原始缺口：{task.gap || "原报告未记录具体缺口，请人工核对。"}</p><p className="text-sm leading-6">原报告建议{task.actionSource === "ai_suggestion" ? "（AI 证据建议）" : task.actionSource === "review" ? "（人工复核后提示）" : task.actionSource === "rules" ? "（本地规则提示）" : ""}：{task.originalAction || "暂无"}</p>{task.actionSource === "ai_suggestion" && !!task.actionCitationIds?.length && <div className="flex flex-wrap gap-3 text-sm">{task.actionCitationIds.map(citation => <Link key={citation} className="text-indigo-700 underline" href={`/reports/${task.baseReportId}#citation-${citation}`}>核对基准引用 {citation}</Link>)}</div>}<p className="font-medium">交付物：{task.plan.deliverable}</p><p className="text-sm">执行步骤</p><ol className="list-decimal space-y-1 pl-5 text-sm">{task.plan.steps.map((s, i) => <li key={i}>{s}</li>)}</ol><p className="text-sm">核验条件</p><ul className="list-disc space-y-1 pl-5 text-sm">{task.plan.acceptanceChecks.map((s, i) => <li key={i}>{s}</li>)}</ul><Link className="text-sm text-indigo-700 underline" href={`/reports/${task.baseReportId}#requirement-${task.requirementId}`}>打开原报告该要求</Link><p className="text-xs leading-6 text-slate-500">此处基准已固定；原报告后来复核不改写它。整份报告重新分析，下面会逐项展示变化。</p></section>
      <section className="panel space-y-4"><h2 className="text-lg font-semibold">2. 上传并关联明确的材料版本</h2><p className="text-sm leading-6 text-slate-600">前往材料中心，给原项目上传具名新版或新增运行/贡献材料；解析完成后回到任务并读取。只改文件名但内容相同不能作为补证变化。</p><Link className="text-indigo-700 underline" href={`/portfolio?growthTask=${task.id}`}>前往上传新版材料 →</Link><fieldset disabled={busy || !growthCanSelect(task)} className="space-y-4"><ResumeVersionPicker resumes={resumes} selectedId={resumeId} onChange={setResumeId} /><ProjectVersionPicker projects={projects} selectedIds={projectIds} onChange={setProjectIds} /><button className="btn-secondary" disabled={!resumeId} onClick={() => void perform(() => api.growthMaterials(task.id, { resumeVersionId: resumeId, projectVersionIds: projectIds }))}>保存本次材料选择</button></fieldset><ul className="space-y-1 text-xs leading-6 text-slate-600">{task.materials.map(m => <li key={`${m.kind}:${m.id}`} className="break-all">已保存：{m.title} · 第{m.versionNumber}版 · {m.materialRole === "reference" ? "第三方参考，不计评级" : m.kind === "resume" ? "简历" : "个人作品"}<br />版本 {m.id} · 摘要 {m.contentHash}</li>)}</ul></section>
      {task.materials.length > 0 && !task.analysisTaskId && <section className="panel space-y-4"><h2 className="text-lg font-semibold">3. 生成新报告</h2><p className="text-sm leading-6 text-slate-600">使用已保存版本和岗位当前要求，生成本人私有报告，不自动更新或再次投递给企业。AI解释需要单独确认；未授权时仅依据本地规则生成，不外发材料。</p><label className="flex items-start gap-2 text-sm leading-6"><input className="mt-1" type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)} /><span>我同意将本次岗位要求、规则结论和脱敏后的必要证据片段发送给 DeepSeek 官方 API 生成带引用解释；不主动加入账号身份、完整简历或原始文件。自由文本脱敏可能遗漏未标记信息，请先核对材料。</span></label><button className="btn" disabled={busy} onClick={() => void perform(() => api.analyzeGrowth(task.id, consent))}>生成新报告</button></section>}
      {task.analysisTaskId && <section className="panel space-y-3"><p className="text-sm">{task.analysisError || (task.targetReportId ? "新报告已保存，可核对变化。" : "材料选择已固定，可读取处理记录和结果。")}</p><Link className="text-sm text-indigo-700 underline" href={`/tasks/${task.analysisTaskId}`}>查看处理记录</Link>{task.targetReportId && <Link className="ml-4 text-sm text-indigo-700 underline" href={`/reports/${task.targetReportId}`}>打开新报告</Link>}</section>}
      <GrowthComparison task={task} />
      <p className="text-xs leading-6 text-slate-500">{task.boundary}</p>
    </>}
  </div>;
}
