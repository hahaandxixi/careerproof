"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ApplicationView, type ProjectHistory, type ResumeHistory } from "@/lib/api/client";
import { applicationReplyInfo } from "@/lib/application-display";
import { displayJobTitle } from "@/lib/demo-display-identity.js";
import { CATEGORY_LABELS, type CareerPlanResult, type ReportSummary } from "@/lib/api/domain";
import { jobWorkspaceNextStep } from "@/lib/job-workspace-next-step";

type WorkspaceState = {
  versions: Parameters<typeof jobWorkspaceNextStep>[0]["versions"];
  report: ReportSummary | null | undefined;
  reply?: ApplicationView;
  replyCount: number;
  tasksIncomplete: boolean;
};

export default function JobWorkspaceNextStep({ refreshVersion, onOpenReply, onViewReplies }: {
  refreshVersion: number;
  onOpenReply: (id: string) => void;
  onViewReplies: () => void;
}) {
  const [state, setState] = useState<WorkspaceState | null>(null);
  const [plan, setPlan] = useState<CareerPlanResult | null | undefined>(undefined);
  const [planFailed, setPlanFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    void Promise.allSettled([
      api.listResumes(), api.listProjects(), api.listReports(1, 1, { scope: "product", view: "jobs" }),
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
        report: reports.status === "fulfilled" ? (reports.value.items[0] ?? null) : undefined,
        tasksIncomplete: [resumes, projects, applications].some(result => result.status === "rejected"),
      });
    });
    return () => { current = false; };
  }, [refreshVersion, revision]);

  useEffect(() => {
    let active = true;
    setPlanFailed(false);
    void api.latestCareerPlan().then(value => {
      if (active) setPlan(value);
    }).catch(() => { if (active) { setPlan(null); setPlanFailed(true); } });
    return () => { active = false; };
  }, [refreshVersion, revision]);
  const direction = plan?.primaryDirection;
  const next = state && jobWorkspaceNextStep({ versions: state.versions, incomplete: state.tasksIncomplete });
  const task = next?.href?.startsWith("/tasks/") ? next : null;
  const reply = state?.reply;
  const replyInfo = reply && applicationReplyInfo(reply);
  const report = state?.report;
  const retry = () => setRevision(value => value + 1);

  return <>
    <header className="job-workspace-header">
      <h1 className="page-title">求职工作台</h1>
      <div className="job-workspace-recommendation">
        {plan && direction && <span>{CATEGORY_LABELS[direction] ?? direction} · {plan.recommendations.length} 个岗位</span>}
        <Link className="btn-quiet btn-compact" href="/recommendations">职业推荐</Link>
        {planFailed && <span role="status">推荐读取失败 <button className="action-link" type="button" onClick={retry}>重试</button></span>}
      </div>
    </header>
    <section className="job-workspace-actions" aria-label="待办与最近报告">
      {!state && <p role="status">正在读取待办与报告…</p>}
      {reply && replyInfo && <div className="job-workspace-action job-workspace-reply">
        <div>
          <strong>{replyInfo.kind}</strong>
          <p>{displayJobTitle(reply.jobTitle, reply.jobId)}{replyInfo.at && <> · <time dateTime={replyInfo.at}>{new Date(replyInfo.at).toLocaleDateString("zh-CN")}</time></>}</p>
        </div>
        <button type="button" className="btn-secondary btn-compact" onClick={() => onOpenReply(reply.id)}>查看企业回复</button>
        {(state?.replyCount ?? 0) > 1 && <button type="button" className="btn-quiet btn-compact" onClick={onViewReplies}>全部企业回复</button>}
      </div>}
      {task?.href && <div className="job-workspace-action job-workspace-task">
        <p>{task.description}</p>
        <Link className="btn-secondary btn-compact" href={task.href}>{task.action}</Link>
      </div>}
      {state?.tasksIncomplete && <p role="status">部分待办未能读取。 <button type="button" className="action-link" onClick={retry}>重试</button></p>}
      {report && <div className="job-workspace-action job-workspace-report">
        <div>
          <strong>最近报告</strong>
          <Link className="action-link" href={`/reports/${report.id}`}>{displayJobTitle(report.jobTitle, report.jobId)}</Link>
          <time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleDateString("zh-CN")}</time>
        </div>
      </div>}
      {state && report === undefined && <p role="status">报告未能读取。 <button type="button" className="action-link" onClick={retry}>重试</button></p>}
      {report === null && !reply && !task && !state?.tasksIncomplete && next?.href && <div className="job-workspace-action">
        <p>暂无报告</p>
        <Link className="btn-secondary btn-compact" href={next.href}>{next.action}</Link>
      </div>}
    </section>
  </>;
}
