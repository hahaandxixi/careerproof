"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ProjectHistory, type ResumeHistory } from "@/lib/api/client";
import { displayJobTitle } from "@/lib/demo-display-identity.js";
import type { ReportSummary } from "@/lib/api/domain";
import { jobWorkspaceNextStep } from "@/lib/job-workspace-next-step";

type Input = Parameters<typeof jobWorkspaceNextStep>[0];

export default function JobWorkspaceNextStep() {
  const [state, setState] = useState<Input | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    void Promise.allSettled([
      api.listResumes(), api.listProjects(), api.listReports(1, 1, { scope: "product" }),
    ]).then(([resumes, projects, reports]) => {
      if (!current) return;
      const versions = [
        ...(resumes.status === "fulfilled" ? resumes.value : []),
        ...(projects.status === "fulfilled" ? projects.value : []),
      ].flatMap<ResumeHistory["versions"][number] | ProjectHistory["versions"][number]>(material => material.versions);
      const report: ReportSummary | undefined = reports.status === "fulfilled" ? reports.value.items[0] : undefined;
      setState({
        versions,
        report: report && { id: report.id, title: displayJobTitle(report.jobTitle, report.jobId) },
        incomplete: [resumes, projects, reports].some(result => result.status === "rejected"),
      });
    });
    return () => { current = false; };
  }, [revision]);

  const next = state && jobWorkspaceNextStep(state);
  const retry = () => { setState(null); setRevision(value => value + 1); };
  return <section className="job-workspace-next" aria-labelledby="job-workspace-next-label">
    <div className="min-w-0">
      <h2 id="job-workspace-next-label">当前待办</h2>
      <p>{next?.description ?? "正在核对材料与报告…"}</p>
      {state?.incomplete && next?.href && <p className="text-sm" role="status">部分资料暂未读取。 <button type="button" className="action-link" onClick={retry}>重试读取</button></p>}
    </div>
    {next && (next.href
      ? <Link className="btn-secondary" href={next.href}>{next.action} →</Link>
      : <button type="button" className="btn-secondary" onClick={retry}>{next.action}</button>)}
  </section>;
}
