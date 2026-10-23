"use client";

import Link from "next/link";
import ArchivedMaterials from "@/components/ArchivedMaterials";
import LoginLink from "@/components/LoginLink";
import MaterialFileDropzone from "@/components/MaterialFileDropzone";
import { latestMaterialVersions, materialFileError, materialFileSize, type UploadedMaterial } from "@/lib/material-upload";
import GrowthUploadReturn from "@/components/GrowthUploadReturn";
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

function UploadProgress({ item, latest = false, onUploadVersion }: { item: UploadRecord; latest?: boolean; onUploadVersion?: () => void }) {
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
            <h3 className="min-w-0 break-words font-semibold text-slate-800">{item.title}</h3>{latest && <span className="text-xs text-slate-600">最新上传</span>}
          </div>
          <p className="mt-1 break-words text-xs leading-6 text-slate-600">
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
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-indigo-700">
        {onUploadVersion && <button type="button" className="underline" onClick={onUploadVersion}>给这个项目上传新版本</button>}
        {complete && <Link className="btn-secondary" href={`/materials/${item.kind}/${item.versionId}`}>预览解析内容</Link>}
        {item.taskId && <Link className={complete ? "underline" : "btn-secondary"} href={`/tasks/${item.taskId}`}>{failed ? "查看原因 / 重试任务" : "查看处理记录"}</Link>}
        {complete && <Link href="/recommendations">获取职业推荐</Link>}
        {complete && <Link href="/jobs">选择岗位匹配</Link>}
      </div>
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
  const [recentUpload, setRecentUpload] = useState<UploadedMaterial | null>(null);

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
  const historicalUploads = uploads.filter(item => !newestUploads.includes(item));

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
    if (projectSubmitting.current) return;
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
    if (projectSubmitting.current) return;
    setUploadOpen(true);
    requestAnimationFrame(() => { const target = document.getElementById("project-upload-title"); target?.scrollIntoView({ block: "start" }); target?.focus({ preventScroll: true }); });
    rememberAttempt(project ? newProjectAttempt(project.name, project.description, project, projectRole) : null);
    setProjectName(project?.name ?? "");
    setProjectDescription(project?.description ?? "");
    setProjectFile(null);
    setProjectError("");
    const input = document.getElementById("project-file") as HTMLInputElement | null;
    if (input) input.value = "";
  }

  return (
    <div className="space-y-8">
      <Suspense fallback={null}><GrowthUploadReturn uploaded={recentUpload} /></Suspense>
      <div>
        <p className="text-sm font-medium text-indigo-600">学生材料中心</p>
        <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="page-title mt-1">我的材料工作台</h1><button type="button" className="btn" onClick={() => { setUploadOpen(true); requestAnimationFrame(() => { const target = document.getElementById("upload-workspace-title"); target?.scrollIntoView({ block: "start" }); target?.focus({ preventScroll: true }); }); }}>添加材料</button></div>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
          先核对已保存材料，再按需要添加简历、项目或新版本。扫描件和图片由本地 OCR 识别，项目只做安全检查和静态扫描，不执行上传的代码。
        </p>
      </div>

      {historyLoaded && !uploads.length && !projects.length && !historyError
        ? <Link href="/demo" className="block rounded-xl bg-indigo-50 p-4 text-sm text-indigo-700">没有测试材料？下载合成简历和项目 ZIP，按演示指南完成匹配 →</Link>
        : <Link href="/demo" className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">需要练习材料？查看合成示例与下载 →</Link>}
      {notice && <p role="status" className="rounded-xl bg-indigo-50 p-3 text-sm text-indigo-800">{notice}</p>}

      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0 flex-1 basis-48">
            <h2 className="section-title">已保存材料</h2>
            <p className="mt-1 text-sm text-slate-500">默认显示每份材料的最新上传；历史版本保留，生成报告时仍需明确选择。</p>
          </div>
          <button type="button" onClick={() => void loadHistory()} className="min-h-11 shrink-0 whitespace-nowrap text-sm text-indigo-600">刷新列表</button>
        </div>
        {historyError && (
          <p role="alert" className="mb-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
            材料列表暂时无法更新：{historyError}。请点击“刷新列表”重试。
          </p>
        )}
        {!historyLoaded && !historyError && <p className="py-6 text-sm text-slate-500">正在加载已保存材料…</p>}
        {projects.filter(project => !project.versions.length).map(project => <div key={project.id} className="surface-muted mb-3 flex flex-wrap items-center justify-between gap-3 p-4"><div><p className="break-words font-medium">{project.name}</p><p className="text-xs text-slate-600">项目已创建，尚未保存文件。</p></div><button type="button" className="btn-secondary" disabled={projectBusy} onClick={() => selectProject(project)}>继续上传</button></div>)}
        {uploads.length > 0 && (
          <div className="grid gap-3 md:grid-cols-2">
            {newestUploads.map(item => <UploadProgress key={item.key} item={item} latest onUploadVersion={item.kind === "project" ? () => { const project = projects.find(value => value.id === item.resourceId); if (project) selectProject(project); } : undefined} />)}
          </div>
        )}
        {historicalUploads.length > 0 && <details className="mt-4 rounded-xl border border-slate-200 bg-white"><summary className="cursor-pointer p-4 text-sm font-medium text-indigo-700">查看历史版本 · {historicalUploads.length} 项</summary><div className="grid gap-3 border-t border-slate-200 p-4 md:grid-cols-2">{historicalUploads.map(item => <UploadProgress key={item.key} item={item} />)}</div></details>}
        {historyLoaded && !historyError && !uploads.length && !projects.length && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center text-sm text-slate-500">
            还没有保存的材料。从下方上传一份简历或一个项目；两类材料可分别准备，不是强制闯关顺序。
          </div>
        )}
      </section>
      <details id="add-materials" open={uploadOpen || !!attempt || (historyLoaded && !uploads.length && !projects.length)} onToggle={event => setUploadOpen(event.currentTarget.open)} className="rounded-2xl border border-slate-200 bg-white">
        <summary className="cursor-pointer p-5 text-base font-semibold text-indigo-700">{uploads.length || projects.length ? "添加材料或上传新版本" : "开始准备材料"}</summary>
        <div className="border-t border-slate-200 p-4 sm:p-5">
          <h2 id="upload-workspace-title" tabIndex={-1} className="mb-3 scroll-mt-32 text-lg font-semibold">添加简历或项目材料</h2><p className="mb-4 text-sm leading-6 text-slate-600">上传前可核对文件、大小、类型和目标。选择文件不会自动提交；解析完成也不会自动加入报告。</p>
      <div className="grid gap-6 lg:grid-cols-2">
        <form onSubmit={submitResume} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-5">
            <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">简历材料</span>
            <h2 className="mt-3 text-xl font-bold text-slate-900">上传简历</h2>
            <p className="mt-1 text-sm text-slate-500">支持 PDF、DOCX、TXT、PNG、JPG/JPEG、WEBP、BMP，最大10MB。OCR 结果需对照原图复核。</p>
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
        </form>

        <form onSubmit={submitProject} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-5">
            <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">项目材料</span>
            <h2 id="project-upload-title" tabIndex={-1} className="mt-3 scroll-mt-32 text-xl font-bold text-slate-900">{attempt?.project ? "继续上传项目" : "上传项目"}</h2>
            <p className="mt-1 text-sm leading-6 text-slate-500">代码项目使用 ZIP（最大30MB），打包前删除 node_modules；作品支持 PDF、DOCX、TXT 和常见图片（最大10MB）。扫描件由本地 OCR 识别，结果需人工核对。</p>
          </div>
          {attempt && (
            <div className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
              <p>{attempt.project ? `正在上传到“${attempt.project.name}”，重试不会重复创建项目。` : "已保留本次提交，可重新选择原文件继续提交。"}</p>
              <p className="mt-1 text-xs">刷新后需重新选择文件；上传状态不确定时请重选原文件。</p>
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
              <label className="flex items-start gap-2"><input type="radio" name="material-role" value="portfolio" checked={(attempt?.materialRole ?? projectRole) === "portfolio"} disabled={projectBusy || !!attempt} onChange={() => setProjectRole("portfolio")} /><span>个人作品：可用于实践证据初评，本人贡献仍需核验</span></label>
              <label className="mt-2 flex items-start gap-2"><input type="radio" name="material-role" value="reference" checked={(attempt?.materialRole ?? projectRole) === "reference"} disabled={projectBusy || !!attempt} onChange={() => setProjectRole("reference")} /><span>第三方参考：可用于检索与学习建议，不计入个人实践评级</span></label>
            </fieldset>
          </div>
          {projectError && <p className="mt-3 text-sm text-rose-600">{projectError}</p>}
          <button
            type="submit"
            disabled={projectBusy || !attemptReady}
            className="mt-5 w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {projectBusy ? "正在提交…" : attempt ? "继续上传（复用原项目）" : "创建项目并开始扫描"}
          </button>
        </form>
      </div>

        </div>
      </details>

      <ArchivedMaterials onRestore={()=>void loadHistory()} />
    </div>
  );
}
