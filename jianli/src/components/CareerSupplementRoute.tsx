import Link from "next/link";
import type { CareerPlanResult, JobRecommendation, MatchReport } from "@/lib/api/domain";

import { sourceLocationId } from "@/lib/source-label";
import { displayJobTitle } from "@/lib/demo-display-identity.js";
import { supplementPlanLines } from "@/lib/report-follow-up";
import EvidenceLink from "./EvidenceLink";
import { CopySupplementAdvice } from "./ReportFollowUpActions";

type Advice = NonNullable<CareerPlanResult["aiPlan"]>["advice"][number];

export default function CareerSupplementRoute({ advice, job, planId, report }: {
  advice: Advice;
  job: JobRecommendation;
  planId: string;
  report?: MatchReport;
}) {
  const plan = advice.taskPlan;
  const gap = advice.keyGap?.trim() || "";
  const task = advice.nextTask?.trim() || "";
  const rationale = advice.reason?.trim() || "";
  const deliverable = plan?.deliverable?.trim() || "";
  const checks = plan?.acceptanceChecks?.filter(check => check.trim()) ?? [];
  const steps = plan?.steps?.filter(step => step.trim()) ?? [];
  const sources = [...new Set(advice.citationIds)].flatMap(id => {
    const evidence = job.evidence.find(source => source.citationId === id);
    return evidence ? [{ id, evidence }] : [];
  });
  const primary = gap || deliverable || task || rationale || checks[0] || steps[0] || "";
  const seen = new Set(primary ? [primary.replace(/\s+/g, " ")] : []);
  const unique = (value?: string) => {
    const text = value?.trim() || "";
    const key = text.replace(/\s+/g, " ");
    if (!text || seen.has(key)) return "";
    seen.add(key);
    return text;
  };
  const detailsDeliverable = unique(deliverable);
  const extraTask = unique(task);
  const reason = unique(rationale);
  const primaryIsCheck = !gap && !deliverable && !task && !rationale && checks.length > 0;
  const primaryIsStep = !gap && !deliverable && !task && !rationale && !checks.length && steps.length > 0;
  const detailChecks = primaryIsCheck ? checks.slice(1) : checks;
  const detailSteps = primaryIsStep ? steps.slice(1) : steps;
  const copyLines = [
    ...(gap && (!deliverable || detailsDeliverable) ? [`待补：${gap}`] : []),
    ...(plan ? supplementPlanLines(plan) : []),
    ...(extraTask || (!gap && !deliverable && task) ? [`建议行动：${task}`] : []),
    ...(reason || (!gap && !deliverable && !task && rationale) ? [`依据：${rationale}`] : []),
  ];

  return <section aria-label="补证建议" className="space-y-3">
    <h3 className="text-base font-semibold">职业规划建议</h3>
    {job.assessedCount === 0 && <p className="text-sm text-amber-800">岗位要求未进入规则评估范围，请人工核对材料。</p>}
    {primary && <div className="reading-band text-sm leading-6" data-reading-tone="amber"><p className="reading-role">{gap ? "待补" : "补证建议"}</p><p className="break-words">{primary}</p></div>}
          {detailsDeliverable && <div><p className="font-medium">提交什么</p><p>{detailsDeliverable}</p></div>}
          {detailSteps.length > 0 && <div>
            <p className="font-medium">执行步骤</p>
            <ol className="list-decimal pl-5">
              {detailSteps.map((step, index) => <li key={index}>{step}</li>)}
            </ol>
          </div>}
          {detailChecks.length > 0 && <div>
            <p className="font-medium">核对项</p>
            <ul className="list-disc pl-5">{detailChecks.map((check, index) => <li key={index}>{check}</li>)}</ul>
          </div>}
    {(reason || extraTask || sources.length > 0) &&
      <details>
        <summary className="reading-band cursor-pointer text-sm font-medium" data-reading-tone="slate">查看补充依据</summary>
        <div className="mt-2 space-y-2 break-words text-sm leading-6 text-slate-700">
          {reason && <p>{reason}</p>}
          {sources.length > 0 && <ul className="flex flex-wrap gap-x-4 gap-y-2" aria-label="判断依据的引用">
            {sources.map(({ id, evidence }) => {
              const label = `${evidence.skill} · ${evidence.filePath.split(/[\\/]/).pop()} · ${evidence.lineStart}–${evidence.lineEnd} 行`;
              const targets = report?.items.flatMap(item => item.evidenceList.flatMap((source, index) =>
                evidence.projectFileId && source.projectFileId === evidence.projectFileId &&
                source.projectVersionId === evidence.projectVersionId && source.lineStart === evidence.lineStart &&
                source.lineEnd === evidence.lineEnd ? [sourceLocationId(item.requirementId, source, index)] : []
              )) ?? [];
              const target = targets.length === 1 ? targets[0] : undefined;
              return <li key={id}>{target ? <EvidenceLink className="action-link" targetId={target}>{label}</EvidenceLink> :
                <Link className="action-link" href={`/recommendations?${new URLSearchParams({ returnPlan: planId })}#plan-citation-${encodeURIComponent(id)}`}>{label}</Link>}</li>;
            })}
          </ul>}
          {extraTask && <p>{extraTask}</p>}

        </div>
      </details>}
    {copyLines.length > 0 && <div className="flex flex-wrap items-center gap-3"><CopySupplementAdvice label="复制规划建议"
      scope={`${planId}:${job.jobId}`}
      text={[`职业规划建议 · ${displayJobTitle(job.jobTitle || report?.jobTitle || "本岗位", job.jobId)}`, ...copyLines].join("\n")} /></div>}
  </section>;
}
