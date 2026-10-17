"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage, type ResumeHistory, type ProjectHistory } from "@/lib/api/client";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS, type JobDetail } from "@/lib/api/domain";
import { applicationNextAction, applicationStatusText } from "@/lib/application-display";
import { bindJobApplicationStatusLifecycle, createJobApplicationStatusSession, type JobApplicationStatusState } from "@/lib/job-application-status";
import { resolveInitialMaterialSelection } from "@/lib/recommendation-selection";
import { useAuth } from "./AuthProvider";
import AccessGate, { ErrorNotice } from "./AccessGate";
import ProjectVersionPicker from "./ProjectVersionPicker";
import ResumeVersionPicker from "./ResumeVersionPicker";

export default function JobDetailView({
  id,
  initialResumeVersionId = "",
  initialProjectVersionIds = [],
}: {
  id: string;
  initialResumeVersionId?: string;
  initialProjectVersionIds?: string[];
}) {
  const { user } = useAuth();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    setJob(null); setError("");
    api.getJob(id).then(value => { if (current) setJob(value); }).catch(reason => { if (current) setError(errorMessage(reason)); });
    return () => { current = false; };
  }, [id, revision, user?.id]);
  if (error) return <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />;
  if (!job) return <p className="py-12 text-center text-slate-500">正在加载岗位…</p>;
  return <div className="space-y-6">
    <Link className="text-sm text-indigo-600" href="/jobs">← 岗位发现</Link>
    <section className="panel"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm text-indigo-600">{CATEGORY_LABELS[job.category] ?? job.category} · {EMPLOYMENT_LABELS[job.employmentType] ?? job.employmentType}</p><h1 className="mt-2 text-3xl font-bold">{job.title}</h1><p className="mt-2 text-sm text-slate-500">{job.companyName} · {job.city || "城市未填写"}</p></div><span className="rounded bg-slate-100 px-3 py-1 text-sm">{job.status === "published" ? "招聘中" : job.status === "draft" ? "草稿" : "已关闭"}</span></div><p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-slate-600">{job.description || "暂无岗位描述"}</p></section>
    <section className="panel"><h2 className="text-lg font-semibold">岗位要求</h2><ol className="mt-4 space-y-3">{job.requirements.map((requirement, index) => <li key={requirement.id} className="rounded-xl bg-slate-50 p-4"><p className="text-sm font-medium">{index + 1}. {requirement.rawText}</p><p className="mt-2 text-xs text-slate-500">{requirement.skillName} · 重要程度 {requirement.weight} / 5 · {requirement.isRequired ? "必要要求" : "加分项"}</p>{requirement.sourceQuote && <p className="mt-2 rounded-lg bg-white p-2 text-xs leading-6 text-slate-600">岗位原文：“{requirement.sourceQuote}”</p>}</li>)}</ol></section>
    {job.status === "published" && (!user || user.role === "student") && <AccessGate roles={["student"]}><MatchForm key={user?.id} job={job} initialResumeVersionId={initialResumeVersionId} initialProjectVersionIds={initialProjectVersionIds} /></AccessGate>}
    {user?.role === "enterprise" && <Link className="panel block text-indigo-700 underline" href={`/jobs/${job.id}/applications`}>查看本岗位已授权投递与匹配对照</Link>}
    {job.status !== "published" && <p className="panel text-sm text-amber-700">该岗位尚未发布或已关闭，目前不能创建新的匹配任务。</p>}
  </div>;
}

// 传智杯56：岗位匹配表单的已有投递提示（无状态展示组件）。只有会话证明的状态才给具体
// 文案并复用 application-display 的共享口径；unknown 不渲染任何结论（绝不显示“未投递”）；
// error 显式且不阻断匹配，重试只读；撤回史如实呈现，不给重投/授权入口。
export function JobApplicationStatusNotice({ state, onRetry }: { state: JobApplicationStatusState; onRetry(): void }) {
  if (state.kind === "loading") return <p role="status" className="mt-3 text-xs text-slate-500">正在核对本岗位的已有投递…</p>;
  if (state.kind === "error") return <p role="alert" className="mt-3 text-xs leading-6 text-rose-700">本岗位投递状态读取失败：{state.message}。这不影响生成报告。<button type="button" className="ml-1 underline" onClick={onRetry}>重试读取</button></p>;
  if (state.kind === "unknown") return null;
  const anchor = `/applications#application-${encodeURIComponent(state.application.id)}`;
  if (state.kind === "withdrawn") return <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs leading-6 text-slate-600"><p>本岗位此前的投递{applicationStatusText(state.application.status)}。这里只说明该条撤回记录；其他投递状态请查看个人投递。生成新报告不受影响；再次分享仍须从报告页确认授权。</p><Link className="text-indigo-700 underline" href={anchor}>查看该条撤回记录 →</Link></div>;
  return <div className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-950"><p className="font-semibold">本岗位已有进行中的投递：{applicationStatusText(state.application.status)}</p><p className="mt-1 text-xs leading-6">下一步：{applicationNextAction(state.application.status)}生成新报告不会替换该投递。</p><Link className="mt-1 block text-indigo-700 underline" href={anchor}>查看本岗位投递状态 →</Link></div>;
}

function MatchForm({
  job,
  initialResumeVersionId,
  initialProjectVersionIds,
}: {
  job: JobDetail;
  initialResumeVersionId: string;
  initialProjectVersionIds: string[];
}) {
  const router = useRouter();
  const [resumes, setResumes] = useState<ResumeHistory[]>([]);
  const [projects, setProjects] = useState<ProjectHistory[]>([]);
  const [resumeVersionId, setResumeVersionId] = useState("");
  const [projectVersionIds, setProjectVersionIds] = useState<string[]>([]);
  const [externalAiConsent, setExternalAiConsent] = useState(false);
  const [usePreviousReport, setUsePreviousReport] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [revision, setRevision] = useState(0);
  // 传智杯56：投递状态读取与材料加载完全解耦——独立会话、独立错误与重试；
  // 状态读取失败只影响提示行，不重置材料、不阻断生成报告。
  const [applicationStatus, setApplicationStatus] = useState<JobApplicationStatusState>({ kind: "loading" });
  const statusSession = useMemo(() => createJobApplicationStatusSession({ api: { myApplications: async () => (await api.myApplications(1, 20, job.id)).items, errorMessage }, publish: setApplicationStatus }), [job.id]);
  useEffect(() => bindJobApplicationStatusLifecycle(statusSession, job.id, { page: window, document }), [statusSession, job.id]);
  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    Promise.all([api.listResumes(), api.listProjects()]).then(([r, p]) => {
      if (!current) return;
      setResumes(r); setProjects(p);
      const selection = resolveInitialMaterialSelection(
        r.flatMap(value => value.versions).filter(version => version.status === "completed").map(version => version.id),
        p.flatMap(value => value.versions).filter(version => version.status === "completed").map(version => version.id),
        initialResumeVersionId,
        initialProjectVersionIds,
      );
      setResumeVersionId(selection.resumeVersionId);
      setProjectVersionIds(selection.projectVersionIds);
    }).catch(reason => { if (current) setError(errorMessage(reason)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [initialProjectVersionIds, initialResumeVersionId, revision]);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (submitting.current || !resumeVersionId) return;
    submitting.current = true; setBusy(true); setError("");
    try { const task = await api.createMatch({ jobId: job.id, resumeVersionId, projectVersionIds, externalAiConsent, usePreviousReport }); router.push(`/tasks/${task.taskId}`); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { submitting.current = false; setBusy(false); }
  }
  const availableResumes = resumes.flatMap(resume => resume.versions.filter(version => version.status === "completed").map(version => ({ ...version, title: resume.title })));
  const selectedResume = availableResumes.find(version => version.id === resumeVersionId);
  const selectedProjects = projects.flatMap(project => project.versions.filter(version => projectVersionIds.includes(version.id)).map(version => `${project.name} · 第 ${version.versionNumber} 版`));
  return <section className="panel"><h2 className="text-lg font-semibold">用我的材料分析岗位匹配</h2><p className="mt-2 text-sm leading-6 text-slate-500">选择已解析完成的版本。报告仅自己可见，生成后再决定是否向企业投递。<Link className="mt-2 block text-indigo-700 underline" href="/applications">已有投递？查看企业回应 →</Link></p>
    <JobApplicationStatusNotice state={applicationStatus} onRetry={() => void statusSession.refresh(job.id)} />
    {error && <div className="mt-4"><ErrorNotice message={error} retry={() => setRevision(value => value + 1)} /></div>}
    {loading ? <p className="mt-4 text-sm text-slate-500">加载我的材料…</p> : <form className="mt-5 space-y-4" onSubmit={submit}>
      <fieldset disabled={busy} className="space-y-4">
        <ResumeVersionPicker resumes={resumes} selectedId={resumeVersionId} onChange={setResumeVersionId} />
        <ProjectVersionPicker projects={projects} selectedIds={projectVersionIds} onChange={setProjectVersionIds} />
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-950">
          <p className="font-semibold">外部 AI 发送范围与脱敏预览</p>
          <p className="mt-2 text-xs leading-6">外部 AI 可选：不勾选下方同意时，只在本站生成规则匹配报告，不发送材料给外部模型。规则报告也可以查看证据并明确投递。</p>
          <dl className="mt-3 grid gap-2 text-xs leading-6 sm:grid-cols-2">
            <div><dt className="font-medium">本次材料</dt><dd>{selectedResume ? `${selectedResume.title} · 第 ${selectedResume.versionNumber} 版` : "尚未选择简历"}{selectedProjects.length ? `；${selectedProjects.join("；")}` : "；未选择项目材料"}</dd></div>
            <div><dt className="font-medium">只发送</dt><dd>{job.requirements.length} 项岗位要求、规则结论和每项最多 3 条必要证据片段</dd></div>
            <div><dt className="font-medium">自动脱敏</dt><dd>邮箱、手机号、身份证号、带“姓名”标签的姓名，以及可识别格式的密码和访问密钥</dd></div>
            <div><dt className="font-medium">不会主动加入</dt><dd>账号身份、个人资料中的姓名、原始文件、完整简历和原始图片</dd></div>
          </dl>
          <p className="mt-3 text-xs leading-6 text-indigo-800">自由文本中的别名、地址，以及未经标记或经过编码的密钥可能无法识别，请只选择与岗位分析必要的材料。没有可引用证据或达到用量上限时，系统会自动生成规则报告。报告只保存在你的账号中，不会自动分享给企业。</p>
          <label className="mt-3 flex items-start gap-2 rounded-lg bg-white/70 p-3 font-medium">
            <input className="mt-1" type="checkbox" checked={externalAiConsent} onChange={event => setExternalAiConsent(event.target.checked)} />
            <span>我已查看上述发送范围，同意将脱敏后的必要片段发送给外部 AI 生成带引用解释。</span>
          </label>
        </div>
        <label className="flex items-start gap-2 text-xs leading-6 text-slate-600"><input className="mt-1" type="checkbox" checked={usePreviousReport} onChange={event => setUsePreviousReport(event.target.checked)} /><span>可选：允许 AI 查询本人同岗位上一份报告的脱敏解释、缺口和最多两条历史片段。历史仅作参考，不作为本轮引用或评级依据；没有历史时只分析当前材料。</span></label>
        <button className="btn" disabled={busy || !resumeVersionId}>{busy ? "创建分析任务…" : "生成我的匹配报告"}</button>
      </fieldset>
    </form>}
  </section>;
}
