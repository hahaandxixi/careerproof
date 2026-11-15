"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { InterviewSessionSummary, Page, ReportSummary } from "@/lib/api/domain";
import { displayJobTitle } from "@/lib/demo-display-identity.js";
import { workspaceStatusLabel } from "@/lib/report-workspace";
import AccessGate, { ErrorNotice } from "./AccessGate";
import { useAuth } from "./AuthProvider";
import ListPagination from "./ListPagination";
import { pageBounds } from "@/lib/list-pagination.js";
import PracticeEntry from "./PracticeEntry";

const reportsPage = (page: number) => api.listReports(page, 12, { scope: "product", view: "jobs" });

function useRead<T>(read: (page: number) => Promise<T>, page = 1) {
  const [revision, setRevision] = useState(0);
  const [response, setResponse] = useState<{ read: typeof read; key: string; data: T | null; error: string }>();
  const key = `${page}:${revision}`;
  useEffect(() => {
    let active = true;
    void read(page).then(
      data => { if (active) setResponse({ read, key, data, error: "" }); },
      reason => { if (active) setResponse({ read, key, data: null, error: errorMessage(reason) }); },
    );
    return () => { active = false; };
  }, [key, page, read]);
  const current = response?.read === read && response.key === key ? response : undefined;
  return { data: current?.data, error: current?.error, busy: !current, retry: () => setRevision(value => value + 1) };
}

export default function InterviewHub() {
  const { user } = useAuth();
  return <AccessGate roles={["student"]}>{user?.role === "student" && <Workspace key={user.id} />}</AccessGate>;
}

function Workspace() {
  return <div className="mx-auto max-w-5xl space-y-6">
    <h1 className="page-title">模拟面试</h1>
    <StartPractice />
    <Sessions />
  </div>;
}

function SessionRow({ session }: { session: InterviewSessionSummary }) {
  return <div className="flex flex-wrap items-center justify-between gap-2 py-2">
    <p className="min-w-0 break-words font-medium">{session.requirementTitle || session.skill || "岗位要求未记录"}</p>
    <Link className="btn-secondary btn-compact" href={`/interview/${session.id}`}>{session.status === "completed" ? "查看结果" : "继续练习"}</Link>
  </div>;
}

function Sessions() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<"pending" | "completed">("pending");
  const [skill, setSkill] = useState("");
  const read = useCallback((page: number) => api.listInterviewSessions(page, 12, status, skill), [status, skill]);
  const { data, busy, error, retry } = useRead(read, page);
  const groups = new Map<string, InterviewSessionSummary>();
  for (const session of data?.items ?? []) {
    const key = session.requirementId ? JSON.stringify([session.jobId, session.requirementId]) : session.id;
    if (!groups.has(key)) groups.set(key, session);
  }
  return <section className="panel space-y-4" aria-labelledby="saved-interviews">
    <h2 id="saved-interviews" className="section-title">我的练习</h2>
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div role="group" aria-label="练习状态" className="flex gap-2">
        {(["pending", "completed"] as const).map(value => <button key={value} type="button"
          className={status === value ? "btn btn-compact" : "btn-secondary btn-compact"}
          aria-pressed={status === value} onClick={() => { setStatus(value); setSkill(""); setPage(1); }}>
          {value === "pending" ? "待继续" : "已完成"}
        </button>)}
      </div>
      <label className="flex flex-wrap items-center gap-2 text-sm">技能
        <select className="field" value={skill} onChange={event => { setSkill(event.target.value); setPage(1); }}>
          <option value="">全部技能</option>
          {(data?.skills ?? (skill ? [skill] : [])).map(value => <option key={value}>{value}</option>)}
        </select>
      </label>
    </div>
    {busy && <p role="status">正在读取练习…</p>}
    {error && <ErrorNotice message={`暂时无法读取已有练习。 ${error}`} retry={retry} />}
    {data?.total === 0 && <p className="text-slate-600">当前筛选下没有练习。</p>}
    {!!groups.size && <ul className="divide-y divide-slate-200">
      {[...groups].map(([key, latest]) => <li key={key} className="py-3">
        <h3 className="break-words text-sm text-slate-600">{displayJobTitle(latest.jobTitle ?? "", latest.jobId) || "岗位名称未记录"}{latest.skill ? ` · ${latest.skill}` : ""}</h3>
        <SessionRow session={latest} />
      </li>)}
    </ul>}
    {data && <ListPagination value={data} busy={busy} label="练习分页" onPage={setPage} />}
  </section>;
}

function StartPractice() {
  const [page, setPage] = useState(1);
  const [jobId, setJobId] = useState("");
  const { data, busy, error, retry } = useRead<Page<ReportSummary>>(reportsPage, page);
  const job = data?.items.find(report => report.jobId === jobId) ?? data?.items[0];
  const bounds = data && pageBounds(data);
  return <section className="panel space-y-4" aria-labelledby="start-interview">
    <h2 id="start-interview" className="section-title">快速开练</h2>
    {busy && <p role="status">正在读取报告…</p>}
    {error && <ErrorNotice message={error} retry={retry} />}
    {data?.total === 0 && <p>还没有保存的报告。<Link href="/reports" className="action-link ml-2">先查看岗位报告</Link></p>}
    {job && <label className="block max-w-xl space-y-1">
      <span className="block font-medium">选择岗位</span>
      <select className="field w-full" value={job.jobId} onChange={event => setJobId(event.target.value)}>
        {data?.items.map(report => <option key={report.jobId} value={report.jobId}>{displayJobTitle(report.jobTitle, report.jobId)}</option>)}
      </select>
    </label>}
    {data && (bounds?.previous || bounds?.next) && <ListPagination value={data} busy={busy} label="岗位分页" onPage={next => { setJobId(""); setPage(next); }} />}
    {job && <ReportVersionChoice key={job.jobId} job={job} />}
  </section>;
}

function ReportVersionChoice({ job }: { job: ReportSummary }) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [reportId, setReportId] = useState(job.id);
  const read = useCallback((page: number) => api.listReports(page, 12, { scope: "product", jobId: job.jobId }), [job.jobId]);
  return <div className="space-y-3">
    {(job.jobReportCount ?? 0) > 1 && <details onToggle={event => setHistoryOpen(event.currentTarget.open)}>
      <summary className="disclosure">切换报告版本</summary>
      {historyOpen && <ReportHistory read={read} page={page} onPage={setPage} selected={reportId} onSelect={setReportId} />}
    </details>}
    <Requirements key={reportId} reportId={reportId} />
  </div>;
}

function ReportHistory({ read, page, onPage, selected, onSelect }: {
  read(page: number): Promise<Page<ReportSummary>>; page: number; onPage(page: number): void; selected: string; onSelect(id: string): void;
}) {
  const { data, busy, error, retry } = useRead(read, page);
  return <div className="space-y-2 py-2">
    {busy && <p role="status">正在读取历史报告…</p>}
    {error && <ErrorNotice message={error} retry={retry} />}
    {!!data?.items.length && <label className="block max-w-xl space-y-1">报告版本
      <select className="field w-full" value={data.items.some(report => report.id === selected) ? selected : ""} onChange={event => { if (event.target.value) onSelect(event.target.value); }}>
        <option value="">选择本页版本</option>
        {data.items.map(report => <option key={report.id} value={report.id}>{new Date(report.createdAt).toLocaleString("zh-CN")}{report.isLatestForJob ? " · 最新" : ""}</option>)}
      </select>
    </label>}
    {data && <ListPagination value={data} busy={busy} label="历史报告分页" onPage={onPage} />}
  </div>;
}

function Requirements({ reportId }: { reportId: string }) {
  const [requirementId, setRequirementId] = useState("");
  const load = useCallback(() => api.getReport(reportId), [reportId]);
  const { data, error, busy, retry } = useRead(load);
  return <div className="space-y-3">
    {busy && <p role="status">正在读取岗位要求…</p>}
    {error && <ErrorNotice message={error} retry={retry} />}
    {data?.items.length === 0 && <p>这份报告没有可练习的岗位要求。</p>}
    {!!data?.items.length && <label className="block max-w-xl space-y-1">
      <span className="block font-medium">选择岗位要求</span>
      <select className="field w-full" value={requirementId} onChange={event => setRequirementId(event.target.value)}>
        <option value="">请选择</option>
        {data.items.map(item => <option key={item.requirementId} value={item.requirementId}>{item.skill ? `${item.skill} · ` : ""}{item.requirementTitle} · {workspaceStatusLabel(item)}</option>)}
      </select>
    </label>}
    {requirementId && data?.items.some(item => item.requirementId === requirementId) && <PracticeEntry key={requirementId} reportId={reportId} requirementId={requirementId} quick />}
  </div>;
}
