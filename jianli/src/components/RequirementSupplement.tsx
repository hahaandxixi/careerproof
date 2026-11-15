"use client";

import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { ACTION_SOURCE_LABELS } from "@/lib/evidence-workspace";
import { followUpGuidance, followUpCopyText } from "@/lib/report-follow-up";
import { workspaceStatusLabel } from "@/lib/report-workspace";
import ReportFollowUpActions from "./ReportFollowUpActions";

/** The supplement item owns the saved advice and the existing copy/upload actions. */
export function RequirementSupplementTarget({ report, item, projectVersionId }: {
  report: MatchReport; item: ReportItem; projectVersionId?: string;
}) {
  const guidance = followUpGuidance(report, item);
  const { gap, action, plan, text } = guidance;
  const focus = gap?.trim() === plan?.deliverable?.trim() ? "" : gap?.trim();
  return <section id={`supplement-${item.requirementId}`} className="panel space-y-3 scroll-mt-24">
    <div className="min-w-0">
      <h3 className="break-words text-lg font-semibold">{item.skill || "岗位要求"} · {workspaceStatusLabel(item)}</h3>
      <p className="mt-1 break-words text-sm leading-6 text-slate-700">{item.requirementTitle}</p>
    </div>
    {(plan || text?.advice || text?.gap || item.aiTaskPlanWarning) && <div className="space-y-3">
      {item.aiTaskPlanWarning && <p role="alert" className="text-sm leading-6 text-amber-900">{item.aiTaskPlanWarning}</p>}
      {(plan || text?.advice) &&
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h4 className="font-semibold text-slate-900">本项已保存的具体要求</h4>
        {action && ACTION_SOURCE_LABELS[action.source] && <span className="text-sm text-slate-600">{ACTION_SOURCE_LABELS[action.source]}</span>}
      </div>}
      {!plan && text?.advice && <p data-reading-tone="blue" className="reading-band whitespace-pre-wrap break-words text-sm leading-7 text-slate-800">{text.advice}</p>}
      {plan ? <div className="space-y-3 text-sm leading-7">
        {focus && <div className="reading-band" data-reading-tone="amber"><p className="reading-role">补证重点</p><p className="whitespace-pre-wrap break-words">{focus}</p></div>}
        {plan.deliverable && <div className="reading-band" data-reading-tone="blue"><p className="reading-role">提交材料</p><p className="whitespace-pre-wrap break-words">{plan.deliverable}</p></div>}
        {plan.acceptanceChecks.length > 0 && <div className="reading-band" data-reading-tone="green"><p className="reading-role">核对条件</p><ul aria-label="核验条件" className="list-disc space-y-1 pl-5">{plan.acceptanceChecks.map((check, index) => <li key={index} className="break-words">{check}</li>)}</ul></div>}
        {plan.steps.length > 0 && <div className="reading-band" data-reading-tone="blue"><p className="reading-role">执行步骤</p>
        <ol aria-label="建议行动" className="list-decimal space-y-2 pl-5">{plan.steps.slice(0, 4).map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol></div>}
        {plan.steps.length > 4 && <details><summary className="cursor-pointer py-2 text-[#1d4a40]">其余执行步骤</summary><ol start={5} className="list-decimal pl-5">{plan.steps.slice(4).map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol></details>}
      </div> : null}
      {action && (text?.gap || (plan && text?.advice)) ? <details className="text-sm leading-7"><summary className="reading-band disclosure" data-reading-tone="amber">报告补充说明</summary><div className="reading-band mt-2" data-reading-tone="amber">
        {plan && text?.advice && <p className="whitespace-pre-wrap break-words">{text.advice}</p>}
        {text?.gap && <p className="whitespace-pre-wrap break-words text-slate-600">{text.gap}</p>}</div>
      </details> : null}
    </div>}
    <div id={`growth-${item.requirementId}`} className="scroll-mt-24">
      <ReportFollowUpActions reportId={report.id} requirementId={item.requirementId} projectVersionId={projectVersionId} text={followUpCopyText(report, item, guidance)} />
    </div>
  </section>;
}
