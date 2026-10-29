"use client";

import type { ReactNode } from "react";
import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { ACTION_SOURCE_LABELS, distinctActionText, evidenceWorkspace } from "@/lib/evidence-workspace";
import { validatedGrowthAdvice } from "@/lib/analysis-status";
import { requirementConclusion, savedRequirementAction } from "@/lib/report-workspace";
import { followUpCopyText, GENERAL_FOLLOW_UP, REVIEW_FOLLOW_UP } from "@/lib/report-follow-up";
import EvidenceLink from "./EvidenceLink";
import ReportFollowUpActions from "./ReportFollowUpActions";
import ReportRequirementReader from "./ReportRequirementReader";

export default function ReportEvidenceWorkspace({ report, children }: { report: MatchReport; children: ReactNode }) {
  return <ReportRequirementReader items={report.items}>{children}</ReportRequirementReader>;
}

export function RequirementActionPanel({ report, item, role, explanationVisible = false }: { report: MatchReport; item: ReportItem; role?: string; explanationVisible?: boolean }) {
  const groups = evidenceWorkspace([item]);
  const supported = groups.supported.length > 0;
  const actionable = groups.gaps.length + groups.partial.length > 0;
  const action = savedRequirementAction(report, item);
  const advice = validatedGrowthAdvice(report, item);
  const plan = advice?.taskPlan;
  const explanation = requirementConclusion(item);
  const gap = advice?.gap || item.evidenceLevelGap?.trim();
  const conclusion = actionable ? gap || action?.evidenceGap?.trim() || explanation : explanation;
  const text = action ? distinctActionText(action, conclusion) : null;
  const allowed = new Set(item.evidenceList.map(source => source.citationId));
  const citations = [...new Set(action?.citationIds ?? [])].filter(id => allowed.has(id));
  return <div className="mt-4 min-w-0 space-y-4" aria-label={`${item.skill}的判断与下一步`}>
    {!explanationVisible && <div><h4 className="text-base font-semibold text-slate-900">{supported ? "当前材料支持" : actionable ? "当前缺口" : "当前需核对"}</h4>
      {/[0-9a-f]{8}-[0-9a-f-]{27,}/i.test(conclusion || "") ? <details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-indigo-700">查看保存的缺口与材料定位原文</summary><p className="mt-2 whitespace-pre-wrap break-words leading-7 text-slate-700">{conclusion}</p></details> : <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">{conclusion || "这项要求尚无已保存的判断说明，请核对岗位原文与材料来源。"}</p>}
      {supported && <p className="mt-2 text-xs leading-6 text-slate-600">材料支持不等于运行成功或本人贡献。</p>}
      {role !== "student" && explanation && explanation !== conclusion && <details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-indigo-700">规则判断原文</summary><p className="mt-2 break-words leading-7">{explanation}</p></details>}
    </div>}
    {item.aiStatus && !["validated", "not_used", "not_requested", "rules_only", "skipped"].includes(item.aiStatus) && <p className="text-sm leading-6 text-amber-900">本项 AI 解释未被采用，当前按规则及复核结果核对。</p>}
    {item.aiTaskPlanWarning && <p role="alert" className="text-sm leading-6 text-amber-900">{item.aiTaskPlanWarning} 已隐藏该任务草稿。</p>}
    {!supported && <div className="space-y-3 border-t border-slate-200 pt-4">
      <h4 className="text-sm font-semibold text-slate-900">{action || plan ? "建议怎么补" : "下一步先核对"}</h4>
      {!plan && text?.advice && <div className="text-sm leading-7"><p className="whitespace-pre-wrap break-words text-slate-800">{text.advice}</p><p className="text-xs text-slate-500">{action && ACTION_SOURCE_LABELS[action.source]} · 已保存建议</p></div>}
      {plan ? <div className="space-y-3 text-sm leading-7">
        <p className="text-sm text-slate-600">以下是建议，尚未执行。</p>
        <ol aria-label="建议行动" className="list-decimal space-y-2 pl-5">{plan.steps.slice(0, 4).map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol>
        {plan.steps.length > 4 && <details><summary className="cursor-pointer py-2 text-indigo-700">其余执行步骤</summary><ol start={5} className="list-decimal pl-5">{plan.steps.slice(4).map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol></details>}
        <details><summary className="cursor-pointer py-1 text-indigo-700">建议提交的材料与核验条件</summary>
        <h5 className="mt-2 font-medium">建议提交的材料</h5>
        <p className="break-words">{plan.deliverable}</p>
        <ul aria-label="核验条件" className="list-disc space-y-1 pl-5">{plan.acceptanceChecks.map((check, index) => <li key={index} className="break-words">{check}</li>)}</ul></details>
      </div> : <div className="space-y-2 text-sm leading-7">
        <p className="reading-copy">先核对已有实现与测试；确有改进后上传新版材料，并主动重新分析。</p>
        <details><summary className="cursor-pointer py-2 text-indigo-700">查看通用核对步骤与材料清单</summary><div className="space-y-2 pt-2">
        <p className="font-medium text-slate-800">通用核对步骤</p>
        <p className="text-xs text-slate-600">以下是操作提示，不是系统已核实的实现情况。在自己的开发工具中完成改进后，返回上传新版材料并主动分析。</p>
        <ol className="list-decimal space-y-2 pl-5">{(actionable ? GENERAL_FOLLOW_UP : REVIEW_FOLLOW_UP).map((step, index) => <li key={index}>{step}</li>)}</ol>
        <p className="font-medium text-slate-800">建议提交的材料</p>
        <p className="text-xs leading-6 text-slate-600">暂无保存的具体交付物要求。以下为通用材料类型，按实际改进选择，不表示系统确认文件已经存在。</p>
        <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-slate-600"><li>直接对应这条要求的新增或修订工程文件，并标明关键位置。</li><li>相关测试材料；如有执行记录，注明源码版本与验证范围。</li><li>必要时提供解释关键操作的项目说明。已有材料先定位，不必重复提交；运行结果与本人贡献分别核验。</li></ul>
        </div></details>
      </div>}
      {action ? <details className="text-sm leading-7"><summary className="cursor-pointer py-2 text-indigo-700">查看报告原始建议 · {ACTION_SOURCE_LABELS[action.source]}</summary>
        {text?.advice && <p className="whitespace-pre-wrap break-words">{text.advice}</p>}
        {text?.gap && <p className="whitespace-pre-wrap break-words text-slate-600">{text.gap}</p>}
        {!text?.advice && !text?.gap && <p className="text-slate-600">原始建议与上方缺口说明相同。</p>}
        <p className="text-xs text-slate-500">来自本报告已保存内容；通用提示不替换原始建议。</p>
      </details> : !plan && <p className="text-xs leading-6 text-slate-600">暂无已保存的具体行动计划。先核对岗位要求和已有材料；不能由此认定实现不存在。</p>}
      {citations.length > 0 && <div className="flex flex-wrap gap-3">{citations.map(id => <EvidenceLink key={id} citationId={id} className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">建议依据 {id}</EvidenceLink>)}</div>}
    </div>}
    {role === "student" && <div>
      {supported ? <details className="border-t border-slate-200 pt-2"><summary className="cursor-pointer py-2 text-sm font-medium text-slate-600">材料有更新？按需查看补证指导</summary><div id={`growth-${item.requirementId}`} className="scroll-mt-24"><ReportFollowUpActions reportId={report.id} requirementId={item.requirementId} text={followUpCopyText(report, item)} /></div></details> : <div id={`growth-${item.requirementId}`} className="scroll-mt-24">
        <ReportFollowUpActions reportId={report.id} requirementId={item.requirementId} text={followUpCopyText(report, item)} />
      </div>}
    </div>}
  </div>;
}
