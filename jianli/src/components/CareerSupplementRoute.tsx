import Link from "next/link";
import type { CareerPlanResult, JobRecommendation } from "@/lib/api/domain";

type Advice = NonNullable<CareerPlanResult["aiPlan"]>["advice"][number];

export default function CareerSupplementRoute({ advice, job, planId }: {
  advice: Advice;
  job: JobRecommendation;
  planId: string;
}) {
  const plan = advice.taskPlan;
  const deliverable = plan?.deliverable?.trim() || "";
  const checks = plan?.acceptanceChecks?.filter(check => check.trim()) ?? [];
  const steps = plan?.steps?.filter(step => step.trim()) ?? [];
  const sources = [...new Set(advice.citationIds)].flatMap(id => {
    const evidence = job.evidence.find(source => source.citationId === id);
    return evidence ? [{ id, evidence }] : [];
  });
  const primary = advice.keyGap?.trim() || deliverable || advice.nextTask?.trim() || advice.reason?.trim() || checks[0] || steps[0] || "";
  const seen = new Set(primary ? [primary.replace(/\s+/g, " ")] : []);
  const unique = (value?: string) => {
    const text = value?.trim() || "";
    const key = text.replace(/\s+/g, " ");
    if (!text || seen.has(key)) return "";
    seen.add(key);
    return text;
  };
  const detailsDeliverable = unique(deliverable);
  const extraTask = unique(advice.nextTask);
  const reason = unique(advice.reason);
  const primaryIsCheck = !advice.keyGap?.trim() && !deliverable && !advice.nextTask?.trim() && !advice.reason?.trim() && checks.length > 0;
  const primaryIsStep = !advice.keyGap?.trim() && !deliverable && !advice.nextTask?.trim() && !advice.reason?.trim() && !checks.length && steps.length > 0;
  const detailChecks = primaryIsCheck ? checks.slice(1) : checks;
  const detailSteps = primaryIsStep ? steps.slice(1) : steps;

  return <section aria-label="补证建议" className="mt-4 space-y-3 border-t border-slate-200 pt-3">
    <h4 className="text-base font-semibold">补证建议</h4>
    {job.assessedCount === 0 && <p className="text-sm text-amber-800">岗位要求未进入规则评估范围，请人工核对材料。</p>}
    {primary && <div className="reading-band text-sm leading-6" data-reading-tone="amber"><p className="reading-role">{advice.keyGap?.trim() ? "待补" : "补证建议"}</p><p className="break-words">{primary}</p></div>}
    {(reason || detailsDeliverable || extraTask || detailSteps.length > 0 || detailChecks.length > 0 || sources.length > 0) &&
      <details>
        <summary className="reading-band cursor-pointer text-sm font-medium" data-reading-tone="slate">查看补证详情与依据</summary>
        <div className="mt-2 space-y-2 break-words text-sm leading-6 text-slate-700">
          {reason && <p>{reason}</p>}
          {detailsDeliverable && <div><p className="font-medium">提交什么</p><p>{detailsDeliverable}</p></div>}
          {sources.length > 0 && <ul className="flex flex-wrap gap-x-4 gap-y-2" aria-label="判断依据的引用">
            {sources.map(({ id, evidence }) => <li key={id}>
              <Link className="action-link" href={`/recommendations?${new URLSearchParams({ returnPlan: planId })}#plan-citation-${encodeURIComponent(id)}`}>
                {evidence.skill} · {evidence.filePath.split(/[\\/]/).pop()} · {evidence.lineStart}–{evidence.lineEnd} 行
              </Link>
            </li>)}
          </ul>}
          {extraTask && <p>{extraTask}</p>}
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
        </div>
      </details>}
  </section>;
}
