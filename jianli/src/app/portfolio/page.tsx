"use client";

import Link from "next/link";
import ArchivedMaterials from "@/components/ArchivedMaterials";
import LoginLink from "@/components/LoginLink";
import MaterialFileDropzone from "@/components/MaterialFileDropzone";
import { latestMaterialVersions, materialFileError, materialFileSize, type UploadedMaterial } from "@/lib/material-upload";
import GrowthUploadReturn from "@/components/GrowthUploadReturn";
import ReportUploadReturn from "@/components/ReportUploadReturn";
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

function UploadProgress({ item, onUploadVersion, onDeleteProject, deleteDisabled = false }: { item: UploadRecord; latest?: boolean; onUploadVersion?: () => void; onDeleteProject?: () => void; deleteDisabled?: boolean }) {
  const complete = item.status === "completed";
  const failed = item.status === "failed" || item.status === "cancelled";
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700"
            >
              {item.kind === "resume" ? "简历" : "项目"}
            </span>
            <h3 className="min-w-0 break-words text-base font-semibold text-slate-800">{item.title}</h3>
          </div>
          <p className="mt-1 break-words text-sm leading-6 text-slate-600">
            {item.filename} · 第 {item.versionNumber} 版 · {new Date(item.createdAt).toLocaleString("zh-CN")}
            {item.sizeBytes != null && ` · ${materialFileSize(item.sizeBytes)}`}
            {item.kind === "project" && ` · ${item.materialRole === "reference" ? "第三方参考" : "个人作品"}`}
          </p>
        </div>
        <span
          className={`text-sm font-medium ${
            complete ? "text-emerald-600" : failed ? "text-rose-600" : "text-indigo-600"
          }`}
        >
          {statusText(item.status)}
        </span>
      </div>

      {!complete && <>
      <div role="progressbar" aria-label={`${item.title}处理进度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.progress} className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all duration-500 ${failed ? "bg-rose-500" : "bg-indigo-600"}`}
          style={{ width: `${Math.max(item.progress, item.status === "pending" ? 4 : 0)}%` }}
        />
      </div>
      <div className="mt-2 flex justify-between gap-3 text-xs text-slate-500">
        <span>{item.errorMessage || item.currentStep}</span>
        <span>{item.progress}%</span>
      </div>
      </>}
      {!item.taskId && !complete && (
        <p className="mt-2 text-xs text-amber-700">历史版本未关联任务，无法恢复实时进度。</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-indigo-700">
        {complete && <Link className="btn-secondary" href={`/materials/${item.kind}/${item.versionId}`}>查看内容</Link>}
        {onUploadVersion && <button type="button" className="btn-secondary" onClick={onUploadVersion}>上传新版</button>}
        {!complete && item.taskId && <Link className="btn-secondary" href={`/tasks/${item.taskId}`}>{failed ? "查看原因 / 重试任务" : "查看处理记录"}</Link>}
      </div>
      <details className="mt-2 text-sm text-slate-600"><summary className="w-fit cursor-pointer py-2">更多操作</summary><div className="flex flex-wrap gap-4 py-2">{item.taskId && <Link className="underline" href={`/tasks/${item.taskId}`}>处理记录</Link>}{onDeleteProject && <button type="button" className="min-h-11 text-sm text-rose-700 underline disabled:opacity-50" disabled={deleteDisabled} onClick={onDeleteProject}>移出材料库</button>}</div></details>
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

  const newestUploads = useMemo(() => latestMaterialVersions(uploads), [uploads]);

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
    requestAnimationFrame(() => { const target = document.getElementById("project-upload-title"); target?.scrollIntoView({ block: "start" }); target?.focus({ preventScroll: true }); });
    rememberAttempt(project ? newProjectAttempt(project.name, project.description, project, projectRole) : null);
    setProjectName(project?.name ?? "");
    setProjectDescription(project?.description ?? "");
    setProjectFile(null);
    setProjectError("");
    const input = document.getElementById("project-file") as HTMLInputElement | null;
    if (input) input.value = "";
  }

  async function deleteProject(projectId: string, name: string) {
    if (projectSubmitting.current || deletingProject.current) return;
    if (!window.confirm(`将项目“${name}”及其所有版本移出当前材料库？历史报告、已授权投递和引用文件仍保留，可在归档材料中恢复。`)) return;
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
      setNotice(`项目“${name}”已从当前材料库移除，历史报告和引用仍保留。`);
    } catch (reason) {
      setDeleteError(`移除项目失败：${errorMessage(reason)}`);
    } finally {
      deletingProject.current = false;
      setDeletingProjectId(null);
    }
  }

  return (
    <div className="material-workspace space-y-5">
      <Suspense fallback={null}><GrowthUploadReturn uploaded={recentUpload} /></Suspense>
      <Suspense fallback={null}><ReportUploadReturn uploaded={recentUpload} /></Suspense>
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="page-title">我的材料</h1><div className="flex items-center gap-4"><Link href="/jobs" className="text-sm text-indigo-700 underline">选择岗位</Link><button type="button" className="btn" disabled={projectBusy||resumeBusy} onClick={() => { setUploadKind(null); setUploadOpen(true); requestAnimationFrame(() => { const target = document.getElementById("upload-workspace-title"); target?.scrollIntoView({ block: "start" }); target?.focus({ preventScroll: true }); }); }}>添加材料</button></div></div>
      </div>

      {historyLoaded && !uploads.length && !projects.length && !historyError
        ? <Link href="/demo" className="block rounded-xl bg-indigo-50 p-4 text-sm text-indigo-700">没有测试材料？下载合成简历和项目 ZIP，按演示指南完成匹配 →</Link>
        : <Link href="/demo" className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">需要练习材料？查看合成示例与下载 →</Link>}
      {notice && <p role="status" className="rounded-xl bg-indigo-50 p-3 text-sm text-indigo-800">{notice}</p>}

      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <button type="button" onClick={() => void loadHistory()} className="min-h-11 shrink-0 whitespace-nowrap text-sm text-indigo-600">刷新列表</button>
        </div>
        {historyError && (
          <p role="alert" className="mb-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
            材料列表暂时无法更新：{historyError}。请点击“刷新列表”重试。
          </p>
        )}
        {!historyLoaded && !historyError && <p className="py-6 text-sm text-slate-500">正在加载已保存材料…</p>}
        {deleteError && <p role="alert" className="mb-3 text-sm text-rose-700">{deleteError}</p>}
        {deletingProjectId && <p role="status" className="mb-3 text-sm text-slate-600">正在移除项目…</p>}
        {projects.filter(project => !project.versions.length).map(project => <div key={project.id} className="surface-muted mb-3 flex flex-wrap items-center justify-between gap-3 p-4"><div><p className="break-words font-medium">{project.name}</p><p className="text-xs text-slate-600">项目已创建，尚未保存文件。</p></div><div className="flex flex-wrap items-center gap-3"><button type="button" className="btn-secondary" disabled={projectBusy || !!deletingProjectId} onClick={() => selectProject(project)}>继续上传</button><button type="button" className="min-h-11 text-sm text-rose-700 underline disabled:opacity-50" disabled={projectBusy || !!deletingProjectId} onClick={() => void deleteProject(project.id, project.name)}>删除项目</button></div></div>)}
        {uploads.length > 0 && (
          <div className="grid gap-3 md:grid-cols-2">
            {newestUploads.map(item => <section key={item.key} className="min-w-0"><UploadProgress item={item} latest onUploadVersion={item.kind === "project" ? () => { const project = projects.find(value => value.id === item.resourceId); if (project) selectProject(project); } : undefined} onDeleteProject={item.kind === "project" ? () => void deleteProject(item.resourceId, item.title) : undefined} deleteDisabled={projectBusy || !!deletingProjectId} />{uploads.some(v=>v.kind===item.kind&&v.resourceId===item.resourceId&&v.key!==item.key)&&<details className="mt-2 text-sm"><summary className="cursor-pointer py-2 text-indigo-700">历史版本</summary><div className="space-y-2">{uploads.filter(v=>v.kind===item.kind&&v.resourceId===item.resourceId&&v.key!==item.key).map(version=><UploadProgress key={version.key} item={version}/>)}</div></details>}</section>)}
          </div>
        )}
        {historyLoaded && !historyError && !uploads.length && !projects.length && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center text-sm text-slate-500">
            暂无材料，请添加简历或项目。
          </div>
        )}
      </section>
      {uploadOpen && <section id="add-materials" className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between gap-3"><h2 id="upload-workspace-title" tabIndex={-1} className={`${uploadKind ? "sr-only" : "text-lg font-semibold"} scroll-mt-24`}>添加材料</h2><button type="button" className="ml-auto min-h-11 text-sm text-slate-600 underline" disabled={resumeBusy||projectBusy} onClick={()=>setUploadOpen(false)}>收起</button></div>
          {!uploadKind&&<div className="flex flex-wrap gap-3"><button type="button" className="btn-secondary" onClick={()=>{setResumeFile(null);setUploadKind("resume");}}>简历</button><button type="button" className="btn-secondary" onClick={()=>selectProject(null)}>新项目</button>{attempt&&<button type="button" className="btn-secondary" onClick={()=>setUploadKind("project")}>继续上次上传</button>}</div>}
      <div className="max-w-3xl">
        {uploadKind === "resume" && <form onSubmit={submitResume} className="min-w-0">
          <div className="mb-5">
            <h2 className="mt-3 text-xl font-bold text-slate-900">上传简历</h2>
          </div>
          <div className="space-y-4">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">简历名称</span>
              <input
                required
                maxLength={200}
                value={resumeTitle}
                onChange={(event) => setResumeTitle(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </label>
            <MaterialFileDropzone id="resume-file" kind="resume" file={resumeFile} target={resumeTitle.trim() || "新简历"} disabled={resumeBusy} onChange={setResumeFile} onError={setResumeError} />
          </div>
          {resumeError && <p className="mt-3 text-sm text-rose-600">{resumeError}</p>}
          <button
            type="submit"
            disabled={resumeBusy}
            className="mt-5 w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {resumeBusy ? "正在上传…" : "上传并解析简历"}
          </button>
        </form>}

        {uploadKind === "project" && <form onSubmit={submitProject} className="min-w-0">
          <div className="mb-5">
            <h2 id="project-upload-title" tabIndex={-1} className="mt-3 scroll-mt-32 text-xl font-bold text-slate-900">{attempt?.project ? "上传新版本" : "上传项目"}</h2>
          </div>
          {attempt && (
            <div className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
              <p>{attempt.project ? `目标项目：${attempt.project.name}` : "已保留未完成上传，请重新选择原文件继续。"}</p>
              {projectError&&<p className="mt-1">重试将复用原项目和上传标识，请选择原文件。</p>}
              <button type="button" disabled={projectBusy} onClick={() => selectProject(null)} className="mt-2 underline">
                改为创建另一个项目
              </button>
            </div>
          )}
          <div className="space-y-4">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">项目名称</span>
              <input
                required
                maxLength={200}
                value={projectName}
                disabled={projectBusy || !!attempt}
                onChange={(event) => setProjectName(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
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
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                placeholder="你负责了什么，解决了什么问题"
              />
            </label>
            <MaterialFileDropzone id="project-file" kind="project" file={projectFile} target={attempt?.project ? `${attempt.project.name} · 新版本` : projectName.trim() ? `${projectName.trim()} · 新项目` : "新项目（请先填写名称）"} disabled={projectBusy} onChange={setProjectFile} onError={setProjectError} />
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
            className="mt-5 w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {projectBusy ? "正在上传…" : projectError&&attempt ? "重试上传" : attempt?.project ? "上传新版本" : "上传项目"}
          </button>
        </form>}
      </div>

      </section>}

      <ArchivedMaterials onRestore={()=>void loadHistory()} />
    </div>
  );
}
