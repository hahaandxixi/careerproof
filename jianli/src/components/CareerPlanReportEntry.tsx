"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { CareerPlanResult, ReportSummary } from "@/lib/api/domain";
import { planMatchesReport } from "@/lib/career-plan-report";
import { jobAnalysisHref } from "@/lib/recommendation-selection";

export default function CareerPlanReportEntry({ plan, jobId }: { plan: CareerPlanResult; jobId: string }) {
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function findReports() {
    setBusy(true); setError("");
    try {
      const first = await api.listReports(1, 100, { jobId, scope: "product", view: "reports" });
      const all = [...first.items];
      for (let page = 2; page <= Math.ceil(first.total / first.pageSize); page++) {
        all.push(...(await api.listReports(page, 100, { jobId, scope: "product", view: "reports" })).items);
      }
      const matches = all.filter(report => planMatchesReport(plan, report, jobId));
      if (matches.length === 1) router.push(href(matches[0].id));
      else setReports(matches);
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  }
  const href = (id: string) => `/reports/${id}?${new URLSearchParams({ careerPlan: plan.planId!, careerJob: jobId })}#report-supplement`;
  return <div className="mt-4 space-y-2">
    <button type="button" className="btn-secondary" disabled={busy} onClick={() => void findReports()}>{busy ? "正在查找报告…" : "在报告中查看补证建议"}</button>
    {error && <p role="alert">{error}</p>}
    {reports?.length === 0 && <p className="text-sm">没有使用相同材料版本的岗位报告。<Link className="action-link ml-2" href={jobAnalysisHref(jobId, plan.materials.find(m => m.kind === "resume")?.id ?? "", plan.materials.filter(m => m.kind === "project").map(m => m.id))}>前往岗位，选择材料并分析</Link></p>}
    {reports && reports.length > 1 && <ul className="space-y-2" aria-label="选择报告">{reports.map(report => <li key={report.id}><Link className="action-link" href={href(report.id)}>报告 · {new Date(report.createdAt).toLocaleString("zh-CN")}</Link></li>)}</ul>}
  </div>;
}
