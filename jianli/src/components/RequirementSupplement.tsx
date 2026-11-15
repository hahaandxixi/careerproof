"use client";

import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { ACTION_SOURCE_LABELS } from "@/lib/evidence-workspace";
import { followUpGuidance, followUpCopyText } from "@/lib/report-follow-up";
import { workspaceStatusLabel } from "@/lib/report-workspace";
import ReportFollowUpActions from "./ReportFollowUpActions";
import SupplementPlanDetails from "./SupplementPlanDetails";

/** The supplement item owns the saved advice and the existing copy/upload actions. */
export function RequirementSupplementTarget({ report, item, projectVersionId }: {
  report: MatchReport; item: ReportItem; projectVersionId?: string;
}) {
  const guidance = followUpGuidance(report, item);
  const { gap, action, plan, text } = guidance;
  const focus = gap?.trim() === plan?.deliverable?.trim() ? "" : gap?.trim();
  return <section id={`supplement-${item.requirementId}`} className="space-y-3 border-t border-brand-line py-5 scroll-mt-24">
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
      {!plan && text?.advice && <p className="whitespace-pre-wrap break-words text-slate-800">{text.advice}</p>}
      {plan && <>
        {focus && <div><p className="font-medium">补证重点</p><p className="whitespace-pre-wrap break-words">{focus}</p></div>}
        <SupplementPlanDetails {...plan} />
      </>}
      {action && (text?.gap || (plan && text?.advice)) ? <details><summary className="disclosure">报告补充说明</summary><div className="mt-2 space-y-2 text-slate-700">
        {plan && text?.advice && <p className="whitespace-pre-wrap break-words">{text.advice}</p>}
        {text?.gap && <p className="whitespace-pre-wrap break-words text-slate-600">{text.gap}</p>}</div>
      </details> : null}
    </div>}
    <div id={`growth-${item.requirementId}`} className="scroll-mt-24">
      <ReportFollowUpActions reportId={report.id} requirementId={item.requirementId} projectVersionId={projectVersionId} text={followUpCopyText(report, item, guidance)} />
    </div>
  </section>;
}
