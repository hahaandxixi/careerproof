"use client";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { CareerPlanResult, MatchReport } from "@/lib/api/domain";
import { planMatchesReport } from "@/lib/career-plan-report";
import CareerSupplementRoute from "./CareerSupplementRoute";

export default function ReportCareerAdvice({ report, planId, jobId }: { report: MatchReport; planId: string; jobId: string }) {
  const [plan, setPlan] = useState<CareerPlanResult | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setPlan(null); setError("");
    api.getCareerPlan(planId).then(value => {
      if (!active) return;
      if (value.planId !== planId || !planMatchesReport(value, report, jobId)) setError("规划与报告的岗位或材料版本不一致，未展示规划建议。");
      else setPlan(value);
    }, reason => { if (active) setError(errorMessage(reason)); });
    return () => { active = false; };
  }, [planId, jobId, report]);
  if (error) return <p role="alert">{error}</p>;
  if (!plan) return <p role="status">正在读取职业规划建议…</p>;
  const advice = plan.aiPlan?.advice.find(item => item.jobId === jobId);
  const job = plan.recommendations.find(item => item.jobId === jobId);
  if (!advice || !job) return <p>该规划没有可采用的岗位建议。</p>;
  return <section className="panel"><p className="text-sm">职业规划建议 · 岗位级</p><CareerSupplementRoute advice={advice} job={job} planId={planId} /></section>;
}
