"use client";

import { displayMaterialTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import ArchivedMaterials from "@/components/ArchivedMaterials";
import LoginLink from "@/components/LoginLink";
import MaterialFileDropzone from "@/components/MaterialFileDropzone";
import { latestMaterialVersions, materialFileError, materialFileSize, type UploadedMaterial } from "@/lib/material-upload";
import GrowthUploadReturn from "@/components/GrowthUploadReturn";
import ReportUploadReturn from "@/components/ReportUploadReturn";
import MaterialUploadIntent from "@/components/MaterialUploadIntent";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { ErrorNotice } from "@/components/AccessGate";
import {
  api,
  errorMessage,
  type ProjectHistory,
  type ResumeHistory,
  type ProjectView,
} from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import {
  newProjectAttempt, readAttempt, writeAttempt, submitProjectAttempt, type ProjectAttempt,
} from "@/lib/portfolio-upload";

interface UploadRecord {
  key: string;
  kind: "resume" | "project";
  title: string;
  filename: string;
  resourceId: string;
  versionId: string;
  taskId: string | null;
  status: string;
  versionNumber: number;
  materialRole?: "portfolio" | "reference" | null;
  createdAt: string;
  progress: number;
  currentStep: string;
  errorMessage?: string;
  sizeBytes?: number | null;
}

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

function statusText(status: string): string {
  const labels: Record<string, string> = {
    pending: "等待处理",
    running: "正在分析",
    completed: "分析完成",
    failed: "分析失败",
    cancelled: "已取消",
  };
  return labels[status] ?? "历史处理状态待确认";
}

function UploadProgress({ item, reportVersions, onUploadVersion, onDeleteProject, deleteDisabled = false }: { item: UploadRecord; reportVersions?: number[]; onUploadVersion?: () => void; onDeleteProject?: () => void; deleteDisabled?: boolean }) {
  const title = displayMaterialTitle(item.title, item.versionId);
  const complete = item.status === "completed";
  const failed = item.status === "failed" || item.status === "cancelled";
  return (
    <article className="material-register-row">
      <div className="material-row-heading">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-sm text-slate-600">{item.kind === "resume" ? "简历" : "项目"}</span>
          <h3 className="min-w-0 break-words text-base font-semibold text-slate-900">{title}</h3>
        </div>
        <p className="mt-1 break-words text-sm leading-6 text-slate-600">
          <span className="break-all">{item.filename}</span>
          {item.sizeBytes != null && <span className="whitespace-nowrap"> · {materialFileSize(item.sizeBytes)}</span>}
          {item.kind === "project" && <span className="whitespace-nowrap"> · {item.materialRole === "reference" ? "第三方参考" : "个人作品"}</span>}
        </p>
      </div>
      <div className="text-sm leading-6 text-slate-700">
        <span className="whitespace-nowrap">{reportVersions ? "当前" : ""}第 {item.versionNumber} 版</span>
        {reportVersions && <p className="mt-1 text-[#173c34]">原报告使用第 {reportVersions.join("、")} 版</p>}
      </div>
      <p className={`text-sm font-medium leading-6 ${complete ? "text-emerald-700" : failed ? "text-rose-700" : "text-[#1d4a40]"}`}>{statusText(item.status)}</p>
      <time className="text-sm leading-6 text-slate-600" dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString("zh-CN")}</time>
      <div className="material-row-actions">
        {complete && <Link className="action-link" href={`/materials/${item.kind}/${item.versionId}`}>查看内容</Link>}
        {onUploadVersion && <button type="button" className="btn-secondary" onClick={onUploadVersion}>上传新版</button>}
        {!complete && item.taskId && <Link className={failed ? "btn" : "btn-secondary"} href={`/tasks/${item.taskId}`}>{failed ? "查看原因 / 重试任务" : "查看处理记录"}</Link>}
        <details className="text-sm text-slate-600"><summary className="disclosure">更多操作</summary><div className="flex flex-wrap gap-2 py-2">{item.taskId && <Link className="btn-secondary" href={`/tasks/${item.taskId}`}>处理记录</Link>}{onDeleteProject && <button type="button" className="btn-danger-quiet" disabled={deleteDisabled} onClick={onDeleteProject}>移出材料库</button>}</div></details>
      </div>
      {!complete && <div className="material-row-progress">
      <div className="flex items-center gap-3">
        <div role="progressbar" aria-label={`${title}处理进度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.progress} className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full transition-all duration-500 ${failed ? "bg-rose-500" : "bg-[#1d4a40]"}`}
            style={{ width: `${Math.max(item.progress, item.status === "pending" ? 4 : 0)}%` }}
          />
        </div>
        <span className="shrink-0 text-xs tabular-nums text-slate-500">{item.progress}%</span>
      </div>
      <div className="mt-2 text-xs">
        <span className={`block break-words ${failed ? "font-medium text-rose-700" : "text-slate-500"}`}>{item.errorMessage || item.currentStep}</span>
      </div>
      {!item.taskId && !complete && (
        <p className="mt-2 text-xs text-amber-700">历史版本未关联任务，无法恢复实时进度。</p>
      )}
      </div>}
    </article>
  );
}

export default function PortfolioPage() {
  const { user, status, error, reload } = useAuth();
  if (status === "loading") {
    return <div className="py-20 text-center text-sm text-slate-500">正在确认登录状态…</div>;
  }
  if (status === "error") return <ErrorNotice message={`暂时无法确认会话：${error}`} retry={() => void reload()} />;
  if (!user) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h1 className="text-xl font-bold text-slate-900">请先登录</h1>
        <p className="mt-2 text-sm text-slate-500">登录学生账号后才能查看和上传自己的材料。</p>
        <LoginLink className="btn mt-5 inline-flex">前往登录</LoginLink>
      </div>
    );
  }
  if (user.role !== "student") {
    return <p className="rounded-xl bg-amber-50 p-8 text-center text-amber-800">请使用学生账号管理个人材料。</p>;
  }
  // Changing accounts unmounts all personal history, pending files and async page state.
  return <PortfolioWorkspace key={user.id} userId={user.id} />;
}

function PortfolioWorkspace({ userId }: { userId: string }) {
  const [resumeTitle, setResumeTitle] = useState("求职简历");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [projectRole, setProjectRole] = useState<"portfolio" | "reference">("portfolio");
  const [projectFile, setProjectFile] = useState<File | null>(null);
  const [resumeBusy, setResumeBusy] = useState(false);
  const [projectBusy, setProjectBusy] = useState(false);
  const [resumeError, setResumeError] = useState("");
  const [projectError, setProjectError] = useState("");
  const [resumes, setResumes] = useState<ResumeHistory[]>([]);
  const [projects, setProjects] = useState<ProjectHistory[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState<ProjectAttempt | null>(null);
  const attemptRef = useRef<ProjectAttempt | null>(null);
  const projectSubmitting = useRef(false);
  const [attemptReady, setAttemptReady] = useState(false);
  const historyRequest = useRef(0);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadKind, setUploadKind] = useState<"resume" | "project" | null>(null);
  const [recentUpload, setRecentUpload] = useState<UploadedMaterial | null>(null);
  const [reportMaterials, setReportMaterials] = useState<MatchReport["materials"]>();
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const deletingProject = useRef(false);

  const rememberAttempt = useCallback((next: ProjectAttempt | null) => {
    attemptRef.current = next;
    setAttempt(next);
    writeAttempt(window.sessionStorage, userId, next);
  }, [userId]);

  useEffect(() => {
    const saved = readAttempt(window.sessionStorage, userId);
    attemptRef.current = saved;
    setAttempt(saved);
    if (saved) {
      setUploadKind("project"); setUploadOpen(true);
      setProjectName(saved.name);
      setProjectDescription(saved.description);
      setProjectRole(saved.materialRole);
    }
    setAttemptReady(true);
  }, [userId]);

  const loadHistory = useCallback(async () => {
    const requestNumber = ++historyRequest.current;
    try {
      const [savedResumes, savedProjects] = await Promise.all([api.listResumes(), api.listProjects()]);
      if (requestNumber !== historyRequest.current) return;
      setResumes(savedResumes);
      setProjects(savedProjects);
      setHistoryLoaded(true);
      setHistoryError("");
    } catch (reason) {
      if (requestNumber === historyRequest.current) setHistoryError(errorMessage(reason));
    }
  }, []);

  useEffect(() => { void loadHistory(); }, [loadHistory]);

  const uploads = useMemo<UploadRecord[]>(() => [
    ...resumes.flatMap((resume) => resume.versions.map((version) => ({
      ...version, key: `resume-${version.id}`, kind: "resume" as const,
      title: resume.title, filename: version.originalFilename ?? "历史简历",
      resourceId: resume.id, versionId: version.id, progress: version.progress ?? 0,
      currentStep: version.currentStep ?? statusText(version.status),
      errorMessage: version.errorMessage ?? undefined,
    }))),
    ...projects.flatMap((project) => project.versions.map((version) => ({
      ...version, key: `project-${version.id}`, kind: "project" as const,
      title: project.name, filename: version.originalFilename ?? "历史项目压缩包",
      resourceId: project.id, versionId: version.id, progress: version.progress ?? 0,
      currentStep: version.currentStep ?? statusText(version.status),
      errorMessage: version.errorMessage ?? undefined,
    }))),
  ].sort((a, b) => b.createdAt.localeCompare(a.createdAt)), [resumes, projects]);

  const reportVersions = new Map<string, number[]>();
  for (const material of reportMaterials ?? []) {
    const owned = uploads.find(item => item.kind === material.kind && item.versionId === material.id);
    if (owned) {
      const key = `${owned.kind}:${owned.resourceId}`;
      const versions = reportVersions.get(key) ?? [];
      if (!versions.includes(owned.versionNumber)) reportVersions.set(key, [...versions, owned.versionNumber]);
    }
  }
  const newestUploads = latestMaterialVersions(uploads).sort(
    (a, b) => Number(reportVersions.has(`${b.kind}:${b.resourceId}`)) - Number(reportVersions.has(`${a.kind}:${a.resourceId}`)),
  );
  const hasCompletedMaterial = historyLoaded && !historyError && newestUploads.some(item => item.status === "completed");
  const uploadTarget = attempt?.project && newestUploads.find(item => item.kind === "project" && item.resourceId === attempt.project?.id);
  const targetReportVersions = uploadTarget ? reportVersions.get(`project:${uploadTarget.resourceId}`) : undefined;

  const activeTaskIds = useMemo(
    () => uploads.filter((item) => item.taskId && !TERMINAL_STATUSES.has(item.status)).map((item) => item.taskId),
    [uploads]
  );
  const activeTaskKey = activeTaskIds.join(",");

  useEffect(() => {
    if (!activeTaskKey) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refreshTasks() {
      await loadHistory();
      if (!cancelled) timer = setTimeout(() => void refreshTasks(), 1800);
    }
    timer = setTimeout(() => void refreshTasks(), 1800);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [activeTaskKey, loadHistory]);

  async function submitResume(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResumeError("");
    if (!resumeFile) {
      setResumeError("请选择简历文件");
      return;
    }
    const invalid = materialFileError("resume", resumeFile);
    if (invalid) { setResumeError(invalid); return; }
    setResumeBusy(true);
    try {
      const saved = await api.uploadResume(resumeTitle.trim(), resumeFile);
      setRecentUpload({ kind: "resume", versionId: saved.versionId });
      setNotice("简历已保存，可以在下方查看处理状态。");
      await loadHistory();
      setResumeFile(null);
      const input = document.getElementById("resume-file") as HTMLInputElement | null;
      if (input) input.value = "";
    } catch (reason) {
      setResumeError(errorMessage(reason));
    } finally {
      setResumeBusy(false);
    }
  }

  async function submitProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (projectSubmitting.current || deletingProject.current) return;
    setProjectError("");
    if (!projectFile) {
      setProjectError("请选择项目压缩包或作品文档");
      return;
    }
    const invalid = materialFileError("project", projectFile);
    if (invalid) { setProjectError(invalid); return; }
    if (!projectName.trim()) {
      setProjectError("请填写项目名称");
      return;
    }
    projectSubmitting.current = true;
    setProjectBusy(true);
    try {
      const current = attemptRef.current ?? newProjectAttempt(projectName.trim(), projectDescription.trim(), null, projectRole);
      rememberAttempt(current);
      const saved = await submitProjectAttempt(api, current, projectFile, rememberAttempt);
      setRecentUpload({ kind: "project", versionId: saved.versionId });
      rememberAttempt(null);
      setNotice("项目文件已保存，可以在下方查看处理状态。");
      setProjectName("");
      setProjectDescription("");
      setProjectRole("portfolio");
      setProjectFile(null);
      const input = document.getElementById("project-file") as HTMLInputElement | null;
      if (input) input.value = "";
      await loadHistory();
    } catch (reason) {
      setProjectError(errorMessage(reason));
      // Also reveal a project created before the ZIP request failed or its response was lost.
      await loadHistory();
    } finally {
      projectSubmitting.current = false;
      setProjectBusy(false);
    }
  }

  function selectProject(project: ProjectView | null) {
    if (projectSubmitting.current || deletingProject.current) return;
    setUploadOpen(true);
    setUploadKind("project");
    requestAnimationFrame(() => { const target = document.getElementById("upload-workspace-title"); target?.scrollIntoView({ block: "nearest" }); target?.focus({ preventScroll: true }); });
    const role = newestUploads.find(item=>item.kind==="project"&&item.resourceId===project?.id)?.materialRole ?? projectRole;
    rememberAttempt(project ? newProjectAttempt(project.name, project.description, project, role) : null);
    setProjectName(project?.name ?? "");
    setProjectDescription(project?.description ?? "");
    setProjectFile(null);
    setProjectError("");
    const input = document.getElementById("project-file") as HTMLInputElement | null;
    if (input) input.value = "";
  }

  async function deleteProject(projectId: string, name: string) {
    if (projectSubmitting.current || deletingProject.current) return;
    if (!window.confirm(`将「${name}」及其所有版本移出当前材料库？\n\n可在归档材料中恢复。历史报告、已授权投递和引用文件均保留。`)) return;
    deletingProject.current = true;
    setDeletingProjectId(projectId);
    setDeleteError("");
    setNotice("");
    try {
      await api.archiveMaterial("project", projectId, true);
      // Ignore a list request started before the archive was committed.
      ++historyRequest.current;
      setProjects(current => current.filter(project => project.id !== projectId));
      if (attemptRef.current?.project?.id === projectId) {
        rememberAttempt(null);
        setProjectName("");
        setProjectDescription("");
        setProjectFile(null);
        const input = document.getElementById("project-file") as HTMLInputElement | null;
        if (input) input.value = "";
      }
      setNotice("已移出材料库。历史报告、已授权投递和引用文件均保留。");
    } catch (reason) {
      setDeleteError(`移除项目失败：${errorMessage(reason)}`);
    } finally {
      deletingProject.current = false;
      setDeletingProjectId(null);
    }
  }

  return (
    <div className="review-workspace material-workspace space-y-5">
      <Suspense fallback={null}><GrowthUploadReturn uploaded={recentUpload} /></Suspense>
      <Suspense fallback={null}><MaterialUploadIntent projects={projects} ready={historyLoaded && attemptReady} onOpen={projectId => {
        if (attemptRef.current || projectSubmitting.current || deletingProject.current || resumeBusy) return false;
        selectProject(projects.find(project => project.id === projectId) ?? null);
        return true;
      }} /></Suspense>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">我的材料</h1>
          {(!historyLoaded || uploads.length > 0 || projects.length > 0 || historyError) &&
            <details className="mt-1 text-sm"><summary className="disclosure">材料帮助</summary><Link href="/demo" className="btn-secondary">示例材料与下载</Link></details>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => void loadHistory()} className="btn-quiet shrink-0 whitespace-nowrap">刷新列表</button>
          {hasCompletedMaterial && <Link href="/jobs" className="btn material-next-action">选择岗位进行对照</Link>}
          <button type="button" className={hasCompletedMaterial ? "btn-secondary" : "btn"} disabled={projectBusy||resumeBusy} onClick={() => { setUploadKind(null); setUploadOpen(true); requestAnimationFrame(() => { const target = document.getElementById("upload-workspace-title"); target?.focus({ preventScroll: true }); }); }}>添加材料</button>
        </div>
      </header>


      {historyLoaded && !uploads.length && !projects.length && !historyError &&
        <Link href="/demo" className="block rounded-xl bg-[#e7efe9] p-4 text-sm text-[#1d4a40]">下载示例简历和项目 ZIP →</Link>}
      {notice && <p role="status" className="rounded-xl bg-[#e7efe9] p-3 text-sm text-[#173c34]">{notice}</p>}

      <div className="material-review-layout">
      <section className="material-register workspace-sheet" aria-labelledby="material-register-title">
        <div className="review-section-heading border-b border-slate-200 pb-3">
          <h2 id="material-register-title" className="section-title">项目与简历</h2>
        </div>
        {historyError && (
          <p role="alert" className="mb-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
            材料列表暂时无法更新：{historyError}。请点击“刷新列表”重试。
          </p>
        )}
        {!historyLoaded && !historyError && <p className="py-6 text-sm text-slate-500">正在加载已保存材料…</p>}
        {deleteError && <p role="alert" className="mb-3 text-sm text-rose-700">{deleteError}</p>}
        {deletingProjectId && <p role="status" className="mb-3 text-sm text-slate-600">正在移除项目…</p>}
        {projects.filter(project => !project.versions.length).map(project => <div key={project.id} className="surface-muted mb-3 flex flex-wrap items-center justify-between gap-3 p-4"><div><p className="break-words font-medium">{displayMaterialTitle(project.name, project.id)}</p><p className="text-sm text-slate-600">项目已创建，尚未保存文件。</p></div><div className="flex flex-wrap items-center gap-3"><button type="button" className="btn-secondary" disabled={projectBusy || !!deletingProjectId} onClick={() => selectProject(project)}>继续上传</button><details className="text-sm text-slate-600"><summary className="disclosure">更多操作</summary><button type="button" className="btn-danger-quiet" disabled={projectBusy || !!deletingProjectId} onClick={() => void deleteProject(project.id, project.name)}>移出材料库</button></details></div></div>)}
        {uploads.length > 0 && (
          <div className="divide-y divide-slate-200">
            <div aria-hidden="true" className="material-register-columns">
              <span>材料名称</span><span>版本</span><span>处理状态</span><span>更新时间</span><span>操作</span>
            </div>
            {newestUploads.map(item => <section key={item.key} className="min-w-0"><UploadProgress item={item} reportVersions={reportVersions.get(`${item.kind}:${item.resourceId}`)} onUploadVersion={item.kind === "project" ? () => { const project = projects.find(value => value.id === item.resourceId); if (project) selectProject(project); } : undefined} onDeleteProject={item.kind === "project" ? () => void deleteProject(item.resourceId, item.title) : undefined} deleteDisabled={projectBusy || !!deletingProjectId} />{uploads.some(v=>v.kind===item.kind&&v.resourceId===item.resourceId&&v.key!==item.key)&&<details className="mt-2 text-sm"><summary className="disclosure">历史版本（{uploads.filter(v=>v.kind===item.kind&&v.resourceId===item.resourceId&&v.key!==item.key).length}）</summary><div className="space-y-2">{uploads.filter(v=>v.kind===item.kind&&v.resourceId===item.resourceId&&v.key!==item.key).map(version=><UploadProgress key={version.key} item={version}/>)}</div></details>}</section>)}
          </div>
        )}
        {historyLoaded && !historyError && !uploads.length && !projects.length && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center text-sm text-slate-500">
            暂无材料，请添加简历或项目。
          </div>
        )}
      </section>
      <aside className="material-review-side min-w-0" aria-label="补证上下文与材料上传">
      <Suspense fallback={null}><ReportUploadReturn uploaded={recentUpload} onMaterials={setReportMaterials} /></Suspense>
      {uploadOpen && <section id="add-materials" className="material-upload-surface">
          <div className="material-upload-heading">
            <h2 id="upload-workspace-title" tabIndex={-1} className="scroll-mt-24 text-lg font-semibold">{uploadKind === "resume" ? "上传简历" : uploadKind === "project" ? (attempt?.project ? "上传新版本" : "上传项目") : "添加材料"}</h2>
            <button type="button" className="btn-quiet" disabled={resumeBusy||projectBusy} onClick={()=>setUploadOpen(false)}>收起</button>
          </div>
          <div className="material-upload-kind-switch" role="group" aria-label="上传材料类型">
            <button type="button" aria-pressed={uploadKind === "resume"} onClick={()=>{setUploadKind("resume");setResumeError("");}}>上传简历</button>
            <button type="button" aria-pressed={uploadKind === "project"} onClick={()=>{setUploadKind("project");setProjectError("");}}>上传项目</button>
            {!uploadKind && attempt && <button type="button" onClick={()=>setUploadKind("project")}>继续上次上传</button>}
          </div>
      <div className="max-w-3xl">
        {uploadKind === "resume" && <form onSubmit={submitResume} className="min-w-0">
          <div className="space-y-4">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">简历名称</span>
              <input
                required
                maxLength={200}
                value={resumeTitle}
                onChange={(event) => setResumeTitle(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-[#e7efe9]"
              />
            </label>
            <MaterialFileDropzone id="resume-file" kind="resume" file={resumeFile} target={resumeTitle.trim() || "新简历"} disabled={resumeBusy} onChange={setResumeFile} onError={setResumeError} />
          </div>
          {resumeError && <p className="mt-3 text-sm text-rose-600">{resumeError}</p>}
          <button
            type="submit"
            disabled={resumeBusy}
            className="mt-5 w-full rounded-lg bg-[#1d4a40] px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {resumeBusy ? "正在上传…" : "上传并解析简历"}
          </button>
        </form>}

        {uploadKind === "project" && <form onSubmit={submitProject} className="min-w-0">
          {attempt && (
            <div className="mb-4 border-l-2 border-indigo-300 pl-3 text-sm text-slate-700">
              <p>{attempt.project ? `目标项目：${displayMaterialTitle(attempt.project.name, attempt.project.id)}` : "已保留未完成上传，请重新选择原文件继续。"}</p>
              {uploadTarget && targetReportVersions && <p className="mt-1">原报告使用第 {targetReportVersions.join("、")} 版 · 当前第 {uploadTarget.versionNumber} 版</p>}
              {projectError&&<p className="mt-1">重试将复用原项目和上传标识，请选择原文件。</p>}
              <button type="button" disabled={projectBusy} onClick={() => selectProject(null)} className="btn-secondary mt-2">
                改为创建另一个项目
              </button>
            </div>
          )}
          <div className="space-y-4">
            {!attempt?.project && <>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">项目名称</span>
              <input
                required
                maxLength={200}
                value={projectName}
                disabled={projectBusy || !!attempt}
                onChange={(event) => setProjectName(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-[#e7efe9]"
                placeholder="如：校园二手交易平台"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">项目说明</span>
              <textarea
                rows={2}
                maxLength={5000}
                value={projectDescription}
                disabled={projectBusy || !!attempt}
                onChange={(event) => setProjectDescription(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-[#e7efe9]"
                placeholder="你负责了什么，解决了什么问题"
              />
            </label>
            </>}
            <MaterialFileDropzone id="project-file" kind="project" file={projectFile} target={attempt?.project ? `${displayMaterialTitle(attempt.project.name, attempt.project.id)} · 新版本` : projectName.trim() ? `${projectName.trim()} · 新项目` : "新项目（请先填写名称）"} disabled={projectBusy} onChange={setProjectFile} onError={setProjectError} />
            <fieldset className="rounded-lg border border-slate-200 p-3 text-sm">
              <legend className="px-1 font-medium text-slate-700">材料归属</legend>
              <label className="flex items-start gap-2"><input type="radio" name="material-role" value="portfolio" checked={(attempt?.materialRole ?? projectRole) === "portfolio"} disabled={projectBusy || !!attempt} onChange={() => setProjectRole("portfolio")} /><span>个人作品</span></label>
              <label className="mt-2 flex items-start gap-2"><input type="radio" name="material-role" value="reference" checked={(attempt?.materialRole ?? projectRole) === "reference"} disabled={projectBusy || !!attempt} onChange={() => setProjectRole("reference")} /><span>参考资料（不计个人实践评级）</span></label>
            </fieldset>
          </div>
          {projectError && <p className="mt-3 text-sm text-rose-600">{projectError}</p>}
          <button
            type="submit"
            disabled={projectBusy || !!deletingProjectId || !attemptReady}
            className="mt-5 w-full rounded-lg bg-[#1d4a40] px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {projectBusy ? "正在上传…" : projectError&&attempt ? "重试上传" : attempt?.project ? "上传新版本" : "上传项目"}
          </button>
        </form>}
      </div>

      </section>}
      </aside>
      </div>

      <ArchivedMaterials onRestore={()=>void loadHistory()} />
    </div>
  );
}

