"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ApplicationView, type ProjectHistory, type ResumeHistory } from "@/lib/api/client";
import { applicationReplyInfo } from "@/lib/application-display";
import { displayJobTitle } from "@/lib/demo-display-identity.js";
import type { ReportSummary } from "@/lib/api/domain";
import { jobWorkspaceNextStep } from "@/lib/job-workspace-next-step";

type WorkspaceState = {
  versions: Parameters<typeof jobWorkspaceNextStep>[0]["versions"];
  reports: ReportSummary[] | null;
  reply?: ApplicationView;
  replyCount: number;
  incomplete: boolean;
};

export default function JobWorkspaceNextStep({ refreshVersion, onOpenReply, onViewReplies }: {
  refreshVersion: number;
  onOpenReply: (id: string) => void;
  onViewReplies: () => void;
}) {
  const [state, setState] = useState<WorkspaceState | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    void Promise.allSettled([
      api.listResumes(), api.listProjects(), api.listReports(1, 3, { scope: "product", view: "jobs" }),
      api.myApplications(1, 3, undefined, { view: "action" }),
    ]).then(([resumes, projects, reports, applications]) => {
      if (!current) return;
      const versions = [
        ...(resumes.status === "fulfilled" ? resumes.value : []),
        ...(projects.status === "fulfilled" ? projects.value : []),
      ].flatMap<ResumeHistory["versions"][number] | ProjectHistory["versions"][number]>(material => material.versions);
      const reply = applications.status === "fulfilled"
        ? applications.value.items.find(item => item.status === "replied" && item.replyText?.trim())
        : undefined;
      setState({
        versions, reply, replyCount: applications.status === "fulfilled" ? applications.value.total : 0,
        reports: reports.status === "fulfilled" ? reports.value.items : null,
        incomplete: [resumes, projects, reports, applications].some(result => result.status === "rejected"),
      });
    });
    return () => { current = false; };
  }, [refreshVersion, revision]);

  const next = state && jobWorkspaceNextStep({ versions: state.versions, incomplete: state.incomplete });
  const reply = state?.reply;
  const replyInfo = reply && applicationReplyInfo(reply);
  const showNext = next?.href && (!reply || next.href.startsWith("/tasks/"));
  return <div className="job-workspace-overview">
    <section className="job-workspace-next" aria-labelledby="job-workspace-next-label">
      <h2 id="job-workspace-next-label">当前待办</h2>
      {!state && <p role="status">正在读取待办…</p>}
      {reply && replyInfo && <div className="job-workspace-next-row">
        <div className="min-w-0">
          <strong>{displayJobTitle(reply.jobTitle, reply.jobId)}</strong>
          <p>{replyInfo.kind}{replyInfo.at && <> · <time dateTime={replyInfo.at}>{new Date(replyInfo.at).toLocaleDateString("zh-CN")}</time></>}</p>
        </div>
        <button type="button" className="btn-secondary btn-compact" onClick={() => onOpenReply(reply.id)}>查看企业回复</button>
      </div>}
      {(state?.replyCount ?? 0) > 1 && <button type="button" className="btn-quiet btn-compact" onClick={onViewReplies}>查看全部企业回复</button>}
      {showNext && <div className="job-workspace-next-row">
        <p>{next.description}</p>
        <Link className="btn-secondary btn-compact" href={next.href}>{next.action}</Link>
      </div>}
      {state?.incomplete && <p role="status">部分资料暂未读取。 <button type="button" className="action-link" onClick={() => { setState(null); setRevision(value => value + 1); }}>重试读取</button></p>}
    </section>
    <section className="job-workspace-recent" aria-labelledby="job-workspace-recent-label">
      <div className="job-workspace-next-row">
        <h2 id="job-workspace-recent-label">最近报告</h2>
        <Link className="btn-quiet btn-compact" href="/reports">全部报告</Link>
      </div>
      {!state && <p role="status">正在读取报告…</p>}
      {state?.reports === null && <p>报告暂未读取。</p>}
      {state?.reports?.length === 0 && <p>暂无报告。</p>}
      {!!state?.reports?.length && <ul>{state.reports.map(report => <li key={report.id}>
        <Link className="action-link" href={`/reports/${report.id}`}>{displayJobTitle(report.jobTitle, report.jobId)}</Link>
        <time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleDateString("zh-CN")}</time>
      </li>)}</ul>}
    </section>
  </div>;
}
