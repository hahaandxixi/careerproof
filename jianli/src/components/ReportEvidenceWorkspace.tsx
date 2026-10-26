"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { ACTION_SOURCE_LABELS, distinctActionText, evidenceWorkspace } from "@/lib/evidence-workspace";
import { validatedGrowthAdvice } from "@/lib/analysis-status";
import { requirementConclusion, savedRequirementAction } from "@/lib/report-workspace";
import { sourceLocationId } from "@/lib/source-label";
import EvidenceLink from "./EvidenceLink";
import GrowthTaskStart from "./GrowthTaskStart";
import ReportRequirementReader from "./ReportRequirementReader";

export default function ReportEvidenceWorkspace({ report, children }: { report: MatchReport; children: ReactNode }) {
  return <ReportRequirementReader items={report.items}>{children}</ReportRequirementReader>;
}

export function RequirementActionPanel({ report, item, role }: { report: MatchReport; item: ReportItem; role?: string }) {
  const groups = evidenceWorkspace([item]);
  const supported = groups.supported.length > 0;
  const actionable = groups.gaps.length + groups.partial.length > 0;
  const action = savedRequirementAction(report, item);
  const advice = validatedGrowthAdvice(report, item);
  const explanation = requirementConclusion(item);
  const text = action ? distinctActionText(action, explanation) : null;
  const gap = advice?.gap || item.evidenceLevelGap?.trim();
  const shown = [explanation, text?.advice, text?.gap].map(value => value?.trim());
  const showGap = gap && !shown.includes(gap);
  const allowed = new Set(item.evidenceList.map(source => source.citationId));
  const citations = [...new Set(action?.citationIds ?? [])].filter(id => allowed.has(id));
  const first = item.evidenceList[0];
  const target = first ? sourceLocationId(item.requirementId, first, 0) : `judgement-${item.requirementId}`;
  return <div className="mt-4 min-w-0 space-y-4" aria-label={`${item.skill}的判断与下一步`}>
    <div><h4 className="text-sm font-semibold text-slate-900">{supported ? "当前材料支持" : actionable ? "当前缺口" : "当前需核对"}</h4>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">{explanation || "这项要求尚无已保存的判断说明，请核对岗位原文与材料来源。"}</p>
      {supported && <p className="mt-2 text-xs leading-6 text-slate-600">本报告保存了 {item.evidenceList.length} 条来源。材料支持不等于运行成功、本人贡献或能力认证。</p>}
    </div>
    {item.aiStatus && !["validated", "not_used", "not_requested", "rules_only", "skipped"].includes(item.aiStatus) && <p className="text-sm leading-6 text-amber-900">本项 AI 解释未被采用，当前按规则及复核结果核对。</p>}
    {item.evidenceList.some(source => source.contextComplete === false) && <p className="border-l-2 border-amber-400 pl-3 text-sm leading-6 text-amber-900">部分引用上下文不完整，请展开来源核对；不能据此确认完整实现。</p>}
    {item.aiTaskPlanWarning && <p role="alert" className="text-sm leading-6 text-amber-900">{item.aiTaskPlanWarning} 已隐藏该任务草稿。</p>}
    {supported ? <EvidenceLink targetId={target} className="btn-secondary inline-flex min-h-11 items-center">核对具体证据 →</EvidenceLink> : <div className="space-y-3 border-t border-slate-200 pt-4">
      <h4 className="text-sm font-semibold text-slate-900">{action ? "建议补证计划" : "下一步先核对"}</h4>
      {action && (text?.advice || text?.gap) ? <>
        {text.advice && <p className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-800">{text.advice}</p>}
        {text.gap && <p className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-600">{text.gap}</p>}
        <p className="text-xs text-slate-500">{ACTION_SOURCE_LABELS[action.source] ?? "来源未标注"} · 来自本报告已保存内容</p>
      </> : <p className="text-sm leading-7 text-slate-600">暂无已保存的具体行动计划。先核对岗位要求和已有材料；不能由此认定实现不存在。</p>}
      {showGap && <p className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-600"><strong>还需核对：</strong>{gap}</p>}
      {advice?.taskPlan && <dl className="space-y-2 text-sm leading-7">
        <div><dt className="font-medium">建议交付物</dt><dd className="break-words">{advice.taskPlan.deliverable}</dd></div>
        <div><dt className="font-medium">执行步骤</dt><dd><ol className="list-decimal space-y-1 pl-5">{advice.taskPlan.steps.map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol></dd></div>
        <div><dt className="font-medium">核验成果</dt><dd><ul className="list-disc space-y-1 pl-5">{advice.taskPlan.acceptanceChecks.map((check, index) => <li key={index} className="break-words">{check}</li>)}</ul></dd></div>
      </dl>}
      {citations.length > 0 && <div className="flex flex-wrap gap-3">{citations.map(id => <EvidenceLink key={id} citationId={id} className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">建议依据 {id}</EvidenceLink>)}</div>}
      <EvidenceLink targetId={target} className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">核对判断依据与来源 →</EvidenceLink>
    </div>}
    {role === "student" && <div id={`growth-${item.requirementId}`} className="scroll-mt-24">
      {supported ? <details className="border-t border-slate-200 pt-2"><summary className="cursor-pointer py-2 text-sm font-medium text-slate-600">材料有更新？按需规划补证</summary><GrowthTaskStart reportId={report.id} requirementId={item.requirementId} advice={advice} /></details> : <>
        <GrowthTaskStart reportId={report.id} requirementId={item.requirementId} advice={advice} primary={actionable} triggerLabel={actionable ? "从这条缺口开始补证" : "记录核对与补证计划"} />
        <p className="mt-2 text-xs leading-6 text-slate-600">先读取已有任务，由你确认后保存。补充新版 → 明确选择版本 → 生成新报告，原报告和投递快照保留。</p>
      </>}
    </div>}
    {!supported && role === "student" && <Link href="/growth" className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">查看我的补证任务 →</Link>}
  </div>;
}
