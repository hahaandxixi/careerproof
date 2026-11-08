"use client";

import type { ReactNode } from "react";
import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { ACTION_SOURCE_LABELS, distinctActionText, evidenceWorkspace } from "@/lib/evidence-workspace";
import { validatedGrowthAdvice } from "@/lib/analysis-status";
import { compactSourceLabel, sourceLocationId } from "@/lib/source-label";
import { requirementConclusion, savedRequirementAction, workspaceStatusLabel } from "@/lib/report-workspace";
import { followUpCopyText, GENERAL_FOLLOW_UP, REVIEW_FOLLOW_UP } from "@/lib/report-follow-up";
import EvidenceLink from "./EvidenceLink";
import ReportFollowUpActions from "./ReportFollowUpActions";
import ReportRequirementReader from "./ReportRequirementReader";

export default function ReportEvidenceWorkspace({ report, children }: { report: MatchReport; children: ReactNode }) {
  return <ReportRequirementReader items={report.items}>{children}</ReportRequirementReader>;
}

export function RequirementActionPanel({ report, item, role, explanationVisible = false, explanationPanel, sourcePanel }: {
  report: MatchReport; item: ReportItem; role?: string; explanationVisible?: boolean;
  explanationPanel?: ReactNode; sourcePanel?: ReactNode;
}) {
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
  const adviceSources = new Set(action?.citationIds ?? []);
  // The AI explanation already renders a locator for its cited sources; do not
  // repeat the exact same file/range directly below it.
  const inlineSources = new Set(explanationVisible ? item.aiCitationIds : []);
  const citationSources = item.evidenceList.filter(source => !source.citationId || !inlineSources.has(source.citationId));
  const projectVersions = report.materials.filter(material => material.kind === "project");
  const projectVersionId = item.evidenceList.find(source => projectVersions.some(material => material.id === source.projectVersionId))?.projectVersionId
    ?? (projectVersions.length === 1 ? projectVersions[0].id : undefined);
  return <div className={`requirement-document ${supported ? "requirement-with-source" : ""} ${item.evidenceList.length ? "requirement-has-sources" : ""}`} aria-label={`${item.skill}的判断与下一步`}>
    <div className="requirement-reading-copy min-w-0 space-y-4">
    <div className="requirement-evidence-flow" aria-label="要求、材料来源与判断关系">
      <div className="requirement-flow-node requirement-flow-requirement"><span>岗位要求</span><strong>{item.skill || item.requirementTitle}</strong></div>
      <span className="requirement-flow-arrow" aria-hidden="true">→</span>
      <div className={`requirement-flow-node ${item.evidenceList.length ? "has-source" : "no-source"}`}><span>材料来源</span><strong>{item.evidenceList.length ? `${compactSourceLabel(item.evidenceList[0], report.materials).fileName} 等 ${item.evidenceList.length} 处` : "未记录可定位材料"}</strong></div>
      <span className="requirement-flow-arrow" aria-hidden="true">→</span>
      <div className={`requirement-flow-node requirement-flow-result ${supported ? "is-supported" : actionable ? "is-gap" : "is-review"}`}><span>当前判断</span><strong>{workspaceStatusLabel(item)}</strong></div>
    </div>
    {explanationPanel}
    {!explanationVisible && <div><h4 className="text-base font-semibold text-slate-900">{supported ? "判断依据" : actionable ? "当前缺口" : "当前需核对"}</h4>
      {/[0-9a-f]{8}-[0-9a-f-]{27,}/i.test(conclusion || "") ? <details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-[#1d4a40]">查看保存的缺口与材料定位原文</summary><p className="mt-2 whitespace-pre-wrap break-words leading-7 text-slate-700">{conclusion}</p></details> : <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">{conclusion || "这项要求尚无已保存的判断说明，请核对岗位原文与材料来源。"}</p>}
      {role !== "student" && explanation && explanation !== conclusion && <details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-[#1d4a40]">规则判断原文</summary><p className="mt-2 break-words leading-7">{explanation}</p></details>}
    </div>}
    {item.aiStatus && !["validated", "not_used", "not_requested", "rules_only", "skipped"].includes(item.aiStatus) && <p className="text-sm leading-6 text-amber-900">本项 AI 解释未被采用，当前按规则及复核结果核对。</p>}
    {item.aiTaskPlanWarning && <p role="alert" className="text-sm leading-6 text-amber-900">{item.aiTaskPlanWarning} 已隐藏该任务草稿。</p>}
    {citationSources.length > 0 && <nav className="requirement-citation-links" aria-label="本项引用">{citationSources.map((source, index) => <EvidenceLink key={sourceLocationId(item.requirementId, source, index)} targetId={sourceLocationId(item.requirementId, source, index)} className="report-citation-chip">{source.citationId && adviceSources.has(source.citationId) && <span className="sr-only">建议依据：</span>}{compactSourceLabel(source, report.materials).fileName} · {source.lineStart}–{source.lineEnd}行 ↗</EvidenceLink>)}</nav>}
    </div>
    {sourcePanel && <div className="requirement-source-context min-w-0">{sourcePanel}</div>}
    {(!supported || role === "student") && <aside className="requirement-next min-w-0 space-y-4" aria-label="补证与后续操作">
    {!supported && <div className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h4 className="font-semibold text-slate-900">{action || plan ? "本项已保存的具体要求" : "以下为通用补证建议"}</h4>
        {action && <span className="text-sm text-slate-600">{ACTION_SOURCE_LABELS[action.source]}</span>}
      </div>
      {!plan && text?.advice && <p className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-800">{text.advice}</p>}
      {plan ? <div className="space-y-3 text-sm leading-7">
        <p className="whitespace-pre-wrap break-words">{plan.deliverable}</p>
        <ul aria-label="核验条件" className="list-disc space-y-1 pl-5">{plan.acceptanceChecks.map((check, index) => <li key={index} className="break-words">{check}</li>)}</ul>
        <p className="font-medium text-slate-800">执行步骤</p>
        <ol aria-label="建议行动" className="list-decimal space-y-2 pl-5">{plan.steps.slice(0, 4).map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol>
        {plan.steps.length > 4 && <details><summary className="cursor-pointer py-2 text-[#1d4a40]">其余执行步骤</summary><ol start={5} className="list-decimal pl-5">{plan.steps.slice(4).map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol></details>}
      </div> : <div className="space-y-2 text-sm leading-7">
        {!text?.advice && <p className="reading-copy">核对已有实现与测试，完善后上传新版材料。</p>}
        <details><summary className="disclosure">通用核对步骤与材料清单</summary><div className="space-y-2 pt-2">
        <p className="text-xs text-slate-600">以下是操作提示，不是系统已核实的实现情况。在自己的开发工具中完成改进后，返回上传新版材料并主动分析。</p>
        <ol className="list-decimal space-y-2 pl-5">{(actionable ? GENERAL_FOLLOW_UP : REVIEW_FOLLOW_UP).map((step, index) => <li key={index}>{step}</li>)}</ol>
        <p className="font-medium text-slate-800">建议提交的材料</p>
        <p className="text-xs leading-6 text-slate-600">以下为通用补证建议，按实际改进选择，不表示系统确认文件已经存在。</p>
        <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-slate-600"><li>与本项要求对应的源码及关键位置。</li><li>如本项要求涉及可执行验证，再提供相关测试文件、复现命令和执行记录；上传材料不等于平台已运行通过。</li><li>仅在多人协作时补充个人贡献说明。已有材料先定位，不必重复提交；运行结果与本人贡献分别核验。</li></ul>
        </div></details>
      </div>}
      {action && (text?.gap || (plan && text?.advice)) ? <details className="text-sm leading-7"><summary className="disclosure">报告补充说明</summary>
        {plan && text?.advice && <p className="whitespace-pre-wrap break-words">{text.advice}</p>}
        {text?.gap && <p className="whitespace-pre-wrap break-words text-slate-600">{text.gap}</p>}
      </details> : null}
    </div>}
    {role === "student" && <div>
      {supported ? <details className="border-t border-slate-200 pt-2"><summary className="cursor-pointer py-2 text-sm font-medium text-slate-600">材料有更新？按需查看补证指导</summary><div id={`growth-${item.requirementId}`} className="scroll-mt-24"><ReportFollowUpActions reportId={report.id} requirementId={item.requirementId} projectVersionId={projectVersionId ?? undefined} text={followUpCopyText(report, item)} /></div></details> : <div id={`growth-${item.requirementId}`} className="scroll-mt-24">
        <ReportFollowUpActions reportId={report.id} requirementId={item.requirementId} projectVersionId={projectVersionId ?? undefined} text={followUpCopyText(report, item)} />
      </div>}
    </div>}
    </aside>}
  </div>;
}
