"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ApplicationView, type ProjectHistory, type ResumeHistory } from "@/lib/api/client";
import { applicationReplyInfo } from "@/lib/application-display";
import { displayJobTitle } from "@/lib/demo-display-identity.js";
import { CATEGORY_LABELS, type CareerPlanResult, type ReportSummary } from "@/lib/api/domain";
import { careerPlanDisplayIdentity, careerPlanRecommendations } from "@/lib/career-plan-display";
import { jobAnalysisHref } from "@/lib/recommendation-selection";
import { jobWorkspaceNextStep } from "@/lib/job-workspace-next-step";

type WorkspaceState = {
  versions: Parameters<typeof jobWorkspaceNextStep>[0]["versions"];
  reports: ReportSummary[] | null;
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
        tasksIncomplete: [resumes, projects, applications].some(result => result.status === "rejected"),
      });
    });
    return () => { current = false; };
  }, [refreshVersion, revision]);

  useEffect(() => {
    let active = true;
    setPlanFailed(false);
    void api.latestCareerPlan().then(value => {
      if (active) setPlan(value && careerPlanDisplayIdentity(value));
    }).catch(() => { if (active) { setPlan(null); setPlanFailed(true); } });
    return () => { active = false; };
  }, [refreshVersion, revision]);
  const jobs = plan ? careerPlanRecommendations(plan, false).slice(0, 2) : [];
  const resume = plan?.materials.find(material => material.kind === "resume");
  const projects = plan?.materials.filter(material => material.kind === "project").map(material => material.id) ?? [];

  const next = state && jobWorkspaceNextStep({ versions: state.versions, incomplete: state.tasksIncomplete });
  const reply = state?.reply;
  const replyInfo = reply && applicationReplyInfo(reply);

  return <div className="job-workspace-overview">
    <section className="job-workspace-next" aria-labelledby="job-workspace-next-label">
      <div className="job-workspace-next-row">
        <h2 id="job-workspace-next-label">职业推荐</h2>
        <Link className="btn-quiet btn-compact" href="/recommendations">{jobs.length ? "查看完整推荐" : "查看推荐"}</Link>
      </div>
      {plan?.primaryDirection && <p>{CATEGORY_LABELS[plan.primaryDirection] ?? plan.primaryDirection}</p>}
      {jobs.length > 0 && <ul className="flex flex-wrap gap-x-4 gap-y-1">{jobs.map(job => <li key={job.jobId}>
        <Link className="action-link" href={resume ? jobAnalysisHref(job.jobId, resume.id, projects) : `/jobs/${encodeURIComponent(job.jobId)}`}>{job.jobTitle}</Link>
      </li>)}</ul>}
      {planFailed ? <p role="status">暂时无法读取推荐。 <button type="button" className="action-link" onClick={() => setRevision(value => value + 1)}>重试读取</button></p>
        : plan === undefined ? <p role="status">正在读取推荐…</p>
        : !jobs.length && <p>{plan?.primaryDirection ? "这份推荐暂无可展示的岗位。" : "暂无已保存的推荐。"}</p>}
      {reply && replyInfo && <div className="job-workspace-next-row">
        <div className="min-w-0">
          <strong>{displayJobTitle(reply.jobTitle, reply.jobId)}</strong>
          <p>{replyInfo.kind}{replyInfo.at && <> · <time dateTime={replyInfo.at}>{new Date(replyInfo.at).toLocaleDateString("zh-CN")}</time></>}</p>
        </div>
        <button type="button" className="btn-secondary btn-compact" onClick={() => onOpenReply(reply.id)}>查看企业回复</button>
      </div>}
      {(state?.replyCount ?? 0) > 1 && <button type="button" className="btn-quiet btn-compact" onClick={onViewReplies}>查看全部企业回复</button>}
      {next?.href?.startsWith("/tasks/") && <div className="job-workspace-next-row">
        <p>{next.description}</p>
        <Link className="btn-secondary btn-compact" href={next.href}>{next.action}</Link>
      </div>}
      {state?.tasksIncomplete && <p role="status">待办暂未完整读取。 <button type="button" className="action-link" onClick={() => { setState(null); setRevision(value => value + 1); }}>重试读取</button></p>}
    </section>
    <section className="job-workspace-recent" aria-labelledby="job-workspace-recent-label">
      <div className="job-workspace-next-row">
        <h2 id="job-workspace-recent-label">最近报告</h2>
        <Link className="btn-quiet btn-compact" href="/reports">全部报告</Link>
      </div>
      {!state && <p role="status">正在读取报告…</p>}
      {state?.reports === null && <p role="status">报告暂未读取。 <button type="button" className="action-link" onClick={() => setRevision(value => value + 1)}>重试读取</button></p>}
      {state?.reports?.length === 0 && <p>暂无报告。</p>}
      {!!state?.reports?.length && <ul>{state.reports.map(report => <li key={report.id}>
        <Link className="action-link" href={`/reports/${report.id}`}>{displayJobTitle(report.jobTitle, report.jobId)}</Link>
        <time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleDateString("zh-CN")}</time>
      </li>)}</ul>}
    </section>
  </div>;
}
