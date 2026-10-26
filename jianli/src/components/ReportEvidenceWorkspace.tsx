"use client";

import { useState, type ReactNode } from "react";
import type { GrowthTask, MatchReport, ReportItem } from "@/lib/api/domain";
import { ACTION_SOURCE_LABELS, distinctActionText, evidenceWorkspace } from "@/lib/evidence-workspace";
import { validatedGrowthAdvice } from "@/lib/analysis-status";
import { requirementConclusion, savedRequirementAction } from "@/lib/report-workspace";
import EvidenceLink from "./EvidenceLink";
import GrowthTaskStart from "./GrowthTaskStart";
import ReportRequirementReader from "./ReportRequirementReader";

export default function ReportEvidenceWorkspace({ report, children }: { report: MatchReport; children: ReactNode }) {
  return <ReportRequirementReader items={report.items}>{children}</ReportRequirementReader>;
}

export function RequirementActionPanel({ report, item, role }: { report: MatchReport; item: ReportItem; role?: string }) {
  const [existingTask, setExistingTask] = useState<GrowthTask | null>(null);
  const groups = evidenceWorkspace([item]);
  const supported = groups.supported.length > 0;
  const actionable = groups.gaps.length + groups.partial.length > 0;
  const action = savedRequirementAction(report, item);
  const advice = validatedGrowthAdvice(report, item);
  const plan = existingTask?.plan ?? advice?.taskPlan;
  const explanation = requirementConclusion(item);
  const gap = advice?.gap || item.evidenceLevelGap?.trim();
  const conclusion = actionable ? gap || action?.evidenceGap?.trim() || explanation : explanation;
  const text = action ? distinctActionText(action, conclusion) : null;
  const allowed = new Set(item.evidenceList.map(source => source.citationId));
  const citations = [...new Set(action?.citationIds ?? [])].filter(id => allowed.has(id));
  return <div className="mt-4 min-w-0 space-y-4" aria-label={`${item.skill}的判断与下一步`}>
    <div><h4 className="text-sm font-semibold text-slate-900">{supported ? "当前材料支持" : actionable ? "当前缺口" : "当前需核对"}</h4>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">{conclusion || "这项要求尚无已保存的判断说明，请核对岗位原文与材料来源。"}</p>
      {supported && <p className="mt-2 text-xs leading-6 text-slate-600">本报告保存了 {item.evidenceList.length} 条来源。材料支持不等于运行成功、本人贡献或能力认证。</p>}
    </div>
    {item.aiStatus && !["validated", "not_used", "not_requested", "rules_only", "skipped"].includes(item.aiStatus) && <p className="text-sm leading-6 text-amber-900">本项 AI 解释未被采用，当前按规则及复核结果核对。</p>}
    {item.evidenceList.some(source => source.contextComplete === false) && <p className="border-l-2 border-amber-400 pl-3 text-sm leading-6 text-amber-900">部分引用上下文不完整，请展开来源核对；不能据此确认完整实现。</p>}
    {item.aiTaskPlanWarning && <p role="alert" className="text-sm leading-6 text-amber-900">{item.aiTaskPlanWarning} 已隐藏该任务草稿。</p>}
    {(existingTask?.actionNeedsRecheck || existingTask?.taskPlanNeedsRecheck) && <p role="alert" className="text-sm leading-6 text-amber-900">已有任务的建议或计划需要重新核对。{existingTask.taskPlanWarning} 请核对原始来源，不要直接照旧建议重复上传。</p>}
    {!supported && <div className="space-y-3 border-t border-slate-200 pt-4">
      <h4 className="text-sm font-semibold text-slate-900">{action ? "建议补证计划" : "下一步先核对"}</h4>
      {plan ? <div className="space-y-3 text-sm leading-7">
        <p className="text-xs text-slate-500">{existingTask ? "来自本人已保存的补证任务计划" : "来自本报告已校验的 AI 任务草稿"}，仍需本人核对，不表示这些步骤已经执行。</p>
        <ol aria-label="建议行动" className="list-decimal space-y-2 pl-5">{plan.steps.slice(0, 4).map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol>
        {plan.steps.length > 4 && <details><summary className="cursor-pointer py-2 text-indigo-700">其余执行步骤</summary><ol start={5} className="list-decimal pl-5">{plan.steps.slice(4).map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol></details>}
        <h5 className="font-medium">需要准备的证据</h5>
        <p className="break-words">{plan.deliverable}</p>
        <ul aria-label="核验条件" className="list-disc space-y-1 pl-5">{plan.acceptanceChecks.map((check, index) => <li key={index} className="break-words">{check}</li>)}</ul>
      </div> : <div className="space-y-2 text-sm leading-7">
        <p className="font-medium text-slate-800">通用核对步骤</p>
        <p className="text-xs text-slate-600">以下是操作提示，不是系统已核实的实现情况。展开补证入口后，会优先读取已有任务及其保存计划。</p>
        {actionable ? <ol className="list-decimal space-y-2 pl-5">
          <li><strong>检查已有实现：</strong>对照上方要求，在自己的项目中核对相关业务代码与测试。未检索到引用不代表没有实现。</li>
          <li><strong>已有实现：</strong>整理对应文件、关键行和相关测试；如有运行记录，注明对应源码版本与执行范围。已提交的材料只需定位，不必重复上传。</li>
          <li><strong>尚未实现：</strong>先确认实际缺口，再完善相关代码与行为测试；未运行的测试要明确标注，不作为成功结果。</li>
          <li><strong>提交新版材料：</strong>确有新增时上传工程或验证材料，在补证任务中明确选择版本并生成新报告；比较引用和逐项解释，等级不一定变化。</li>
        </ol> : <ol className="list-decimal space-y-2 pl-5">
          <li>对照岗位原文与已有来源，核对规则覆盖范围和本人复核意见；不能由此认定实现不存在。</li>
          <li>记录仍不确定的部分与需要人工核对的材料位置，再决定是否补充新版材料。</li>
        </ol>}
      </div>}
      {action ? <details className="text-sm leading-7"><summary className="cursor-pointer py-2 text-indigo-700">查看报告原始建议 · {ACTION_SOURCE_LABELS[action.source]}</summary>
        {text?.advice && <p className="whitespace-pre-wrap break-words">{text.advice}</p>}
        {text?.gap && <p className="whitespace-pre-wrap break-words text-slate-600">{text.gap}</p>}
        {!text?.advice && !text?.gap && <p className="text-slate-600">原始建议与上方缺口说明相同。</p>}
        <p className="text-xs text-slate-500">来自本报告已保存内容；通用提示不替换原始建议。</p>
      </details> : <p className="text-xs leading-6 text-slate-600">暂无已保存的具体行动计划。先核对岗位要求和已有材料；不能由此认定实现不存在。</p>}
      {citations.length > 0 && <div className="flex flex-wrap gap-3">{citations.map(id => <EvidenceLink key={id} citationId={id} className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">建议依据 {id}</EvidenceLink>)}</div>}
    </div>}
    {role === "student" && <div id={`growth-${item.requirementId}`} className="scroll-mt-24">
      {supported ? <details className="border-t border-slate-200 pt-2"><summary className="cursor-pointer py-2 text-sm font-medium text-slate-600">材料有更新？按需规划补证</summary><GrowthTaskStart reportId={report.id} requirementId={item.requirementId} advice={advice} /></details> : <>
        <GrowthTaskStart reportId={report.id} requirementId={item.requirementId} advice={advice} primary={actionable} triggerLabel={actionable ? "开始补证" : "记录核对与补证计划"} onExistingTask={setExistingTask} showExistingPlan={false} />
        <p className="mt-2 text-xs leading-6 text-slate-600">先读取已有任务，由你确认后保存。补充新版 → 明确选择版本 → 生成新报告，原报告和投递快照保留。</p>
      </>}
    </div>}
  </div>;
}
