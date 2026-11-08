"use client";

import { demoJobAlias, displayJobTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, type CurrentUser, type ProjectHistory, type ResumeHistory } from "@/lib/api/client";
import type { JobSummary, NotificationItem, ReportSummary } from "@/lib/api/domain";
import { useAuth } from "./AuthProvider";
import IdentityName from "./IdentityName";

type SavedWork = {
  reports: ReportSummary[]; notifications: NotificationItem[];
  jobs: JobSummary[]; resumes: ResumeHistory[]; projects: ProjectHistory[];
};
const EMPTY: SavedWork = { reports: [], notifications: [], jobs: [], resumes: [], projects: [] };

export default function HomeWorkspace({ children }: { children: React.ReactNode }) {
  const { user, status, reload } = useAuth();
  if (status === "loading") return <p role="status" className="panel text-slate-600">正在读取你的工作区…</p>;
  if (status === "error") return <div className="space-y-4"><div role="alert" className="surface-muted">暂时无法确认登录状态。<button className="btn-secondary btn-compact ml-2" onClick={() => void reload()}>重试连接</button></div>{children}</div>;
  if (user?.role === "admin") return <section className="panel space-y-4"><h1 className="page-title">管理员工作区</h1><p className="text-sm text-slate-600">按当前账号权限查看岗位与报告。</p><div className="flex flex-wrap gap-3"><Link className="btn" href="/jobs">查看岗位</Link><Link className="btn-secondary" href="/reports">查看报告</Link></div></section>;
  return user ? <SavedWorkspace key={user.id} user={user} /> : <>{children}</>;
}

function SavedWorkspace({ user }: { user: CurrentUser }) {
  const [work, setWork] = useState<SavedWork>(EMPTY);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const student = user.role === "student";
  useEffect(() => {
    let active = true;
    setLoading(true); setErrors([]);
    const requests: { key: keyof SavedWork; label: string; run: () => Promise<SavedWork[keyof SavedWork]> }[] = student ? [
      { key: "reports", label: "最近报告", run: async () => (await api.listReports(1, 3)).items },
      { key: "notifications", label: "未读通知", run: async () => (await api.notifications(1, true, 3)).items },
      { key: "resumes", label: "简历", run: () => api.listResumes() },
      { key: "projects", label: "项目", run: () => api.listProjects() },
    ] : [
      { key: "jobs", label: "我的岗位", run: async () => (await api.listJobs({ page: 1, pageSize: 3 }, true)).items },
      { key: "notifications", label: "未读通知", run: async () => (await api.notifications(1, true, 3)).items },
    ];
    void Promise.allSettled(requests.map(request => request.run())).then(results => {
      if (!active) return;
      const next = { ...EMPTY }; const failures: string[] = [];
      results.forEach((result, index) => {
        const { key, label } = requests[index];
        if (result.status === "fulfilled") Object.assign(next, { [key]: result.value });
        else failures.push(`${label}读取失败：${errorMessage(result.reason)}`);
      });
      setWork(next); setErrors(failures); setLoading(false);
    });
    return () => { active = false; };
  }, [student, reload]);
  const activeMaterial = [...work.resumes, ...work.projects].flatMap(material => material.versions)
    .filter(version => version.taskId && ["pending", "running", "failed"].includes(version.status))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
  const resumeHref = activeMaterial ? `/tasks/${activeMaterial.taskId}` : work.reports[0] ? `/reports/${work.reports[0].id}` : "/portfolio";
  // 主按钮文案保持短句；材料状态与文件名单独成行，避免把长文件名塞进按钮。
  const resumeLabel = activeMaterial ? (activeMaterial.status === "failed" ? "处理上传问题" : "查看材料处理") : work.reports[0] ? "继续核对报告" : errors.length ? "打开我的材料" : "准备第一份材料";
  return <div className="space-y-6">
    <header className="workspace-toolbar border-b border-slate-200 pb-4">
      <h1 className="page-title">{student ? "学生工作台" : "企业工作台"}</h1>
      <p className="workspace-meta"><IdentityName name={user.displayName} identityId={user.id}/></p>
    </header>
    {loading ? <p role="status" className="panel text-sm text-slate-600">正在读取最近保存的工作…</p> : <>
      {errors.length > 0 && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"><p>部分内容未能读取，以下列表可能不完整。</p>{errors.map(error => <p key={error} className="mt-1 break-words">{error}</p>)}<button className="btn-secondary mt-3" onClick={() => setReload(value => value + 1)}>重试读取</button></div>}
      <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <section className="workspace-sheet lg:col-span-2">
          <div className="workspace-toolbar workspace-row items-center">
            <div className="min-w-0"><h2 className="section-title">{student ? "继续工作" : "岗位管理"}</h2>
              {student && activeMaterial ? <p className="workspace-meta break-words">{activeMaterial.status === "failed" ? "处理失败" : activeMaterial.status === "pending" ? "等待处理" : "正在处理"} · {activeMaterial.originalFilename ?? "已上传材料"}</p> :
                student && work.reports[0] ? <p className="workspace-meta">{displayJobTitle(work.reports[0].jobTitle, work.reports[0].jobId)}</p> : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Link className="btn max-w-full text-left" href={student ? resumeHref : "/jobs/mine"}>{student ? resumeLabel : "查看岗位与授权投递"} →</Link>
              <Link className="btn-secondary" href={student ? "/jobs" : "/jobs/new"}>{student ? "探索岗位" : "发布岗位"}</Link>
            </div>
          </div>
        </section>
        {student ? <>
          <WorkSection title="最近报告" href="/reports" empty="没有可显示的报告。先选定材料，再进入岗位生成报告。">
            {work.reports.map(report => <li key={report.id}><Link className="work-row" href={`/reports/${report.id}`}><strong className="block break-words text-sm">{displayJobTitle(report.jobTitle, report.jobId)}</strong><span className="mt-1 block text-xs leading-5 text-slate-600">{new Date(report.createdAt).toLocaleString("zh-CN")} · {report.aiFallbackUsed ? "模型已回退，请核对规则结果" : report.analysisMode === "rules" ? "规则报告" : "查看分析方式与依据"}</span></Link></li>)}
          </WorkSection>
        </> : <WorkSection title="最近岗位" href="/jobs/mine" empty="还没有可显示的岗位。创建岗位后，在岗位管理中核对授权投递。">
          {work.jobs.map(job => <li key={job.id}><Link className="work-row" href={`/jobs/${job.id}/applications`}><strong className="block break-words text-sm">{displayJobTitle(job.title, job.id)}</strong><span className="mt-1 block text-xs leading-5 text-slate-600">{demoJobAlias(job.id)?.companyName ?? job.companyName} · {job.status === "published" ? "已发布" : job.status === "draft" ? "草稿" : "已关闭"} · 核对已授权投递 →</span></Link></li>)}
        </WorkSection>}
        <WorkSection title="未读消息" href="/notifications" empty="当前没有可显示的未读消息。">
          {work.notifications.map(notification => <li key={notification.id}><Link className="work-row" href="/notifications"><span className="flex items-start gap-2">{!notification.readAt && <span aria-hidden="true" className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[#1d4a40]" />}<span className="min-w-0"><strong className="block break-words text-sm">{notification.title}</strong><span className="mt-1 block text-xs leading-5 text-slate-600">{new Date(notification.createdAt).toLocaleString("zh-CN")}</span></span></span></Link></li>)}
        </WorkSection>
        {student && <section className="workspace-toolbar border-t border-slate-200 pt-4 lg:col-span-2"><h2 className="section-title">材料与岗位</h2><div className="flex flex-wrap gap-3"><Link href="/portfolio" className="btn-secondary">管理我的材料</Link><Link href="/recommendations" className="btn-secondary">职业与岗位推荐</Link></div></section>}
      </div>
    </>}
  </div>;
}

function WorkSection({ title, href, empty, children }: { title: string; href: string; empty: string; children: React.ReactNode[] }) {
  return <section className="workspace-sheet px-4 py-3 sm:px-5"><div className="flex items-center justify-between gap-3"><h2 className="section-title">{title}</h2><Link className="btn-secondary shrink-0" href={href} aria-label={`查看全部${title}`}>查看全部</Link></div>{children.length ? <ul className="divide-y divide-slate-100">{children}</ul> : <p className="mt-3 text-sm leading-6 text-slate-600">{empty}</p>}</section>;
}

