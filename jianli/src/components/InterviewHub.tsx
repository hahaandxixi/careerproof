"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { Page, ReportSummary } from "@/lib/api/domain";
import { displayJobTitle } from "@/lib/demo-display-identity.js";
import { practiceStatusLabel } from "@/lib/interview-practice";
import AccessGate, { ErrorNotice } from "./AccessGate";
import { useAuth } from "./AuthProvider";
import ListPagination from "./ListPagination";
import PracticeEntry from "./PracticeEntry";

const reportsPage = (page: number) => api.listReports(page, 12, { scope: "product" });

function useRead<T>(read: (page: number) => Promise<T>, page = 1) {
  const [revision, setRevision] = useState(0);
  const [response, setResponse] = useState<{ key: string; data: T | null; error: string }>();
  const key = `${page}:${revision}`;
  useEffect(() => {
    let active = true;
    void read(page).then(
      data => { if (active) setResponse({ key, data, error: "" }); },
      reason => { if (active) setResponse({ key, data: null, error: errorMessage(reason) }); },
    );
    return () => { active = false; };
  }, [key, page, read]);
  const current = response?.key === key ? response : undefined;
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

function Sessions() {
  const [page, setPage] = useState(1);
  const { data, busy, error, retry } = useRead(api.listInterviewSessions, page);
  return <section className="panel space-y-4" aria-labelledby="saved-interviews">
    <h2 id="saved-interviews" className="section-title">继续练习</h2>
    {busy && <p role="status">正在读取练习…</p>}
    {error && <ErrorNotice message={`暂时无法读取已有练习。 ${error}`} retry={retry} />}
    {data?.total === 0 && <p className="text-slate-600">还没有练习。可以选择一项岗位要求开始。</p>}
    {!!data?.items.length && <ul className="divide-y divide-slate-200">
      {data.items.map(session => {
        const status = session.status === "draft" || session.status === "in_progress" || session.status === "completed"
          ? practiceStatusLabel(session.status) : "状态未记录";
        return <li key={session.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div className="min-w-0">
            <h3 className="break-words font-semibold">{displayJobTitle(session.jobTitle ?? "", session.jobId) || "岗位名称未记录"}</h3>
            <p className="break-words">{session.requirementTitle || session.skill || "岗位要求未记录"}</p>
            <p className="text-sm text-slate-600">{status}{session.needsAttention && session.status !== "completed" ? " · 有待处理的问题" : ""} · <time dateTime={session.updatedAt}>{new Date(session.updatedAt).toLocaleString("zh-CN")}</time></p>
          </div>
          <Link className="btn-secondary" href={`/interview/${session.id}`}>{session.status === "completed" ? "查看结果" : "继续练习"}</Link>
        </li>;
      })}
    </ul>}
    {data && <ListPagination value={data} busy={busy} label="练习分页" onPage={setPage} />}
  </section>;
}

function StartPractice() {
  const [page, setPage] = useState(1);
  const [reportId, setReportId] = useState("");
  const { data, busy, error, retry } = useRead<Page<ReportSummary>>(reportsPage, page);
  return <section className="panel space-y-4" aria-labelledby="start-interview">
    <h2 id="start-interview" className="section-title">开始模拟面试</h2>
    {busy && <p role="status">正在读取报告…</p>}
    {error && <ErrorNotice message={error} retry={retry} />}
    {data?.total === 0 && <p>还没有保存的报告。<Link href="/reports" className="action-link ml-2">先查看岗位报告</Link></p>}
    {!!data?.items.length && <label className="block max-w-xl space-y-1">
      <span className="block font-medium">选择报告</span>
      <select className="field w-full" value={reportId} onChange={event => setReportId(event.target.value)}>
        <option value="">请选择</option>
        {data.items.map(report => <option key={report.id} value={report.id}>
          {displayJobTitle(report.jobTitle, report.jobId)} · {new Date(report.createdAt).toLocaleString("zh-CN")}
        </option>)}
      </select>
    </label>}
    {data && <ListPagination value={data} busy={busy} label="报告分页" onPage={next => { setReportId(""); setPage(next); }} />}
    {reportId && data?.items.some(report => report.id === reportId) && <Requirements key={reportId} reportId={reportId} />}
  </section>;
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
        {data.items.map(item => <option key={item.requirementId} value={item.requirementId}>{item.requirementTitle}</option>)}
      </select>
    </label>}
    {requirementId && data?.items.some(item => item.requirementId === requirementId) && <PracticeEntry key={requirementId} reportId={reportId} requirementId={requirementId} />}
  </div>;
}
