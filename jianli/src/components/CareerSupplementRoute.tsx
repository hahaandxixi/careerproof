import type { MouseEvent } from "react";
import type { CareerPlanResult, JobRecommendation } from "@/lib/api/domain";

type Advice = NonNullable<CareerPlanResult["aiPlan"]>["advice"][number];

export default function CareerSupplementRoute({ advice, job, onEvidence }: {
  advice: Advice;
  job: JobRecommendation;
  onEvidence: (event: MouseEvent<HTMLAnchorElement>, citationId: string) => void;
}) {
  const plan = advice.taskPlan;
  const deliverable = plan?.deliverable?.trim() || advice.nextTask?.trim();
  const checks = plan?.acceptanceChecks?.filter(check => check.trim()) ?? [];
  const steps = plan?.steps?.filter(step => step.trim()) ?? [];
  const sources = [...new Set(advice.citationIds)].flatMap(id => {
    const evidence = job.evidence.find(source => source.citationId === id);
    return evidence ? [{ id, evidence }] : [];
  });
  const stepsInRoute = !checks.length && steps.length > 0;
  const extraTask = advice.nextTask?.trim() !== deliverable ? advice.nextTask?.trim() : "";
  const route = [
    { label: "缺口", content: advice.keyGap?.trim() },
    { label: "提交什么", content: deliverable },
    { label: "如何核对", content: checks[0] },
    { label: "怎么做", content: stepsInRoute ? steps[0] : undefined },
  ].filter(point => point.content);

  return <section aria-label="补证建议" className="mt-4 space-y-3 border-t border-slate-200 pt-3">
    <h4 className="text-base font-semibold">补证建议</h4>
    {job.assessedCount === 0 && <p className="text-sm text-amber-800">岗位要求未进入规则评估范围，请人工核对材料。</p>}
    {route.length > 0 && <ol className="grid gap-3 md:grid-cols-3">
      {route.map(({ label, content }, index) => <li key={label} className="flex min-w-0 items-start gap-2 rounded-lg bg-slate-50 p-3">
        <span aria-hidden="true" className="grid size-6 shrink-0 place-items-center rounded-full bg-indigo-100 text-sm font-semibold text-indigo-800">{index + 1}</span>
        <div className="min-w-0 break-words text-sm leading-6">
          <p className="font-semibold text-slate-900">{label}</p>
          <p className="text-slate-700">{content}</p>
          {label === "如何核对" && checks.length > 1 && <span className="text-slate-600">共 {checks.length} 条核对项</span>}
        </div>
      </li>)}
    </ol>}
    {(advice.reason?.trim() || extraTask || steps.length > Number(stepsInRoute) || checks.length > 1 || sources.length > 0) &&
      <details>
        <summary className="cursor-pointer text-sm font-medium">{checks.length > 1 ? `查看其余 ${checks.length - 1} 条核对项与详情` : "查看判断依据与完整步骤"}</summary>
        <div className="mt-2 space-y-2 break-words text-sm leading-6 text-slate-700">
          {advice.reason?.trim() && <p>{advice.reason}</p>}
          {sources.length > 0 && <ul className="flex flex-wrap gap-x-4 gap-y-2" aria-label="判断依据的引用">
            {sources.map(({ id, evidence }) => <li key={id}>
              <a className="action-link" href={`#plan-citation-${id}`} onClick={event => onEvidence(event, id)}>
                {evidence.skill} · {evidence.filePath.split(/[\\/]/).pop()} · {evidence.lineStart}–{evidence.lineEnd} 行
              </a>
            </li>)}
          </ul>}
          {extraTask && <p>{extraTask}</p>}
          {steps.length > Number(stepsInRoute) && <div>
            <p className="font-medium">执行步骤</p>
            <ol className="list-decimal pl-5" start={stepsInRoute ? 2 : 1}>
              {steps.slice(stepsInRoute ? 1 : 0).map((step, index) => <li key={index}>{step}</li>)}
            </ol>
          </div>}
          {checks.length > 1 && <div>
            <p className="font-medium">其他核对项</p>
            <ul className="list-disc pl-5">{checks.slice(1).map((check, index) => <li key={index}>{check}</li>)}</ul>
          </div>}
        </div>
      </details>}
  </section>;
}
