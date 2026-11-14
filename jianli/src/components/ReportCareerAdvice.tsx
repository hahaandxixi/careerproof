"use client";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { CareerPlanResult, MatchReport } from "@/lib/api/domain";
import { planMatchesReport } from "@/lib/career-plan-report";
import CareerSupplementRoute from "./CareerSupplementRoute";

export default function ReportCareerAdvice({ report, planId, jobId }: { report: MatchReport; planId?: string; jobId: string }) {
  const [plan, setPlan] = useState<CareerPlanResult | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setPlan(null); setError("");
    (planId ? api.getCareerPlan(planId) : api.latestCareerPlan()).then(value => {
      if (!active) return;
      if (!value || (planId && value.planId !== planId) || !planMatchesReport(value, report, jobId)) {
        if (planId) setError("这份规划与本报告的岗位或材料版本不一致。");
      }
      else setPlan(value);
    }, reason => { if (active && planId) setError(errorMessage(reason)); });
    return () => { active = false; };
  }, [planId, jobId, report]);
  if (error) return <p role="alert">{error}</p>;
  if (!plan) return planId ? <p role="status">正在读取职业规划建议…</p> : null;
  const advice = plan.aiPlan?.advice.find(item => item.jobId === jobId);
  const job = plan.recommendations.find(item => item.jobId === jobId);
  if (!advice || !job || !plan.planId) return planId ? <p>该规划没有可采用的岗位建议。</p> : null;
  return <details className="panel"><summary className="disclosure">职业规划建议</summary><CareerSupplementRoute advice={advice} job={job} planId={plan.planId} report={report} /></details>;
}
