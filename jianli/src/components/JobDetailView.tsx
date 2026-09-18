"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, type ResumeHistory, type ProjectHistory } from "@/lib/api/client";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS, type JobDetail } from "@/lib/api/domain";
import { useAuth } from "./AuthProvider";
import AccessGate, { ErrorNotice } from "./AccessGate";

export default function JobDetailView({ id }: { id: string }) {
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
    <section className="panel"><h2 className="text-lg font-semibold">岗位要求</h2><ol className="mt-4 space-y-3">{job.requirements.map((requirement, index) => <li key={requirement.id} className="rounded-xl bg-slate-50 p-4"><p className="text-sm font-medium">{index + 1}. {requirement.rawText}</p><p className="mt-2 text-xs text-slate-500">{requirement.skillName} · 重要程度 {requirement.weight} / 5 · {requirement.isRequired ? "必要要求" : "加分项"}</p></li>)}</ol></section>
    {job.status === "published" && (!user || user.role === "student") && <AccessGate roles={["student"]}><MatchForm key={user?.id} job={job} /></AccessGate>}
    {user?.role === "enterprise" && <p className="panel text-sm text-slate-500">学生可用自己的材料对照此岗位进行分析。当前匹配报告仅供学生本人查看，尚未开放投递和企业查看候选人报告的功能。</p>}
    {job.status !== "published" && <p className="panel text-sm text-amber-700">该岗位尚未发布或已关闭，目前不能创建新的匹配任务。</p>}
  </div>;
}

function MatchForm({ job }: { job: JobDetail }) {
  const router = useRouter();
  const [resumes, setResumes] = useState<ResumeHistory[]>([]);
  const [projects, setProjects] = useState<ProjectHistory[]>([]);
  const [resumeVersionId, setResumeVersionId] = useState("");
  const [projectVersionIds, setProjectVersionIds] = useState<string[]>([]);
  const [externalAiConsent, setExternalAiConsent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    Promise.all([api.listResumes(), api.listProjects()]).then(([r, p]) => {
      if (!current) return;
      setResumes(r); setProjects(p);
      setResumeVersionId(r.flatMap(value => value.versions).find(version => version.status === "completed")?.id ?? "");
      setProjectVersionIds([]);
    }).catch(reason => { if (current) setError(errorMessage(reason)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [revision]);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (submitting.current || !resumeVersionId) return;
    submitting.current = true; setBusy(true); setError("");
    try { const task = await api.createMatch({ jobId: job.id, resumeVersionId, projectVersionIds, externalAiConsent }); router.push(`/tasks/${task.taskId}`); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { submitting.current = false; setBusy(false); }
  }
  const availableResumes = resumes.flatMap(resume => resume.versions.filter(version => version.status === "completed").map(version => ({ ...version, title: resume.title })));
  const selectedResume = availableResumes.find(version => version.id === resumeVersionId);
  const selectedProjects = projects.flatMap(project => project.versions.filter(version => projectVersionIds.includes(version.id)).map(version => `${project.name} · 第 ${version.versionNumber} 版`));
  return <section className="panel"><h2 className="text-lg font-semibold">用我的材料分析岗位匹配</h2><p className="mt-2 text-sm leading-6 text-slate-500">选择已解析完成的版本。报告会固定本次材料版本；项目更新后，旧报告仍保留原始依据。</p>
    {error && <div className="mt-4"><ErrorNotice message={error} retry={() => setRevision(value => value + 1)} /></div>}
    {loading ? <p className="mt-4 text-sm text-slate-500">加载我的材料…</p> : <form className="mt-5 space-y-4" onSubmit={submit}>
      <fieldset disabled={busy} className="space-y-4">
        <label className="block text-sm font-medium">简历版本<select className="field mt-2" required value={resumeVersionId} onChange={e => setResumeVersionId(e.target.value)}><option value="">请选择已完成的简历</option>{availableResumes.map(version => <option key={version.id} value={version.id}>{version.title} · 第 {version.versionNumber} 版 · {version.originalFilename}</option>)}</select></label>
        {!availableResumes.length && <p className="text-sm text-amber-700">还没有可用简历，请先<Link href="/portfolio" className="underline">上传并完成解析</Link>。</p>}
        <div><p className="text-sm font-medium">项目或作品版本（最多 10 项，可不选）</p><div className="mt-2 space-y-2">{projects.map(project => <div key={project.id} className="rounded-lg bg-slate-50 p-3"><p className="text-sm font-medium">{project.name}</p>{project.versions.filter(v => v.status === "completed").map(version => <label key={version.id} className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={projectVersionIds.includes(version.id)} disabled={!projectVersionIds.includes(version.id) && projectVersionIds.length >= 10} onChange={e => setProjectVersionIds(value => e.target.checked ? [...value, version.id] : value.filter(id => id !== version.id))} />第 {version.versionNumber} 版 · {version.originalFilename}</label>)}{!project.versions.some(v => v.status === "completed") && <p className="mt-1 text-xs text-slate-500">暂无完成解析的版本</p>}</div>)}</div>{!projects.length && <p className="mt-2 text-sm text-slate-500">暂无项目或作品，可以先<Link className="text-indigo-600" href="/portfolio">上传材料</Link>。</p>}</div>
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-950">
          <p className="font-semibold">外部 AI 发送范围与脱敏预览</p>
          <dl className="mt-3 grid gap-2 text-xs leading-6 sm:grid-cols-2">
            <div><dt className="font-medium">本次材料</dt><dd>{selectedResume ? `${selectedResume.title} · 第 ${selectedResume.versionNumber} 版` : "尚未选择简历"}{selectedProjects.length ? `；${selectedProjects.join("；")}` : "；未选择项目材料"}</dd></div>
            <div><dt className="font-medium">只发送</dt><dd>{job.requirements.length} 项岗位要求、规则结论和每项最多 3 条必要证据片段</dd></div>
            <div><dt className="font-medium">自动脱敏</dt><dd>邮箱、手机号、身份证号及带“姓名”标签的姓名</dd></div>
            <div><dt className="font-medium">不会主动加入</dt><dd>账号身份、个人资料中的姓名、原始文件、完整简历和原始图片</dd></div>
          </dl>
          <p className="mt-3 text-xs leading-6 text-indigo-800">自由文本中的别名、地址等内容可能无法被格式规则识别，请只选择与岗位分析必要的材料。没有可引用证据或达到用量上限时，系统会自动生成规则报告。报告只保存在你的账号中，不会自动分享给企业。</p>
          <label className="mt-3 flex items-start gap-2 rounded-lg bg-white/70 p-3 font-medium">
            <input className="mt-1" type="checkbox" checked={externalAiConsent} onChange={event => setExternalAiConsent(event.target.checked)} />
            <span>我已查看上述发送范围，同意将脱敏后的必要片段发送给外部 AI 生成带引用解释。</span>
          </label>
        </div>
        <button className="btn" disabled={busy || !resumeVersionId || !externalAiConsent}>{busy ? "创建分析任务…" : "生成我的匹配报告"}</button>
      </fieldset>
    </form>}
  </section>;
}
