"use client";

import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { ACTION_SOURCE_LABELS, distinctActionText } from "@/lib/evidence-workspace";
import { followUpGuidance, followUpCopyText } from "@/lib/report-follow-up";
import { workspaceStatusLabel } from "@/lib/report-workspace";
import EvidenceLink from "./EvidenceLink";
import ReportFollowUpActions from "./ReportFollowUpActions";

/** One explicit entry from the current requirement to its saved supplement item. */
export function RequirementSupplementJump({ item }: { item: ReportItem }) {
  return <EvidenceLink
    targetId={`supplement-${item.requirementId}`}
    className="btn inline-flex min-h-11 items-center"
  >
    查看补证建议
  </EvidenceLink>;
}

/** The supplement item owns the saved advice and the existing copy/upload actions. */
export function RequirementSupplementTarget({ report, item, projectVersionId }: {
  report: MatchReport; item: ReportItem; projectVersionId?: string;
}) {
  const { gap, action, plan } = followUpGuidance(report, item);
  const text = action ? distinctActionText(action, gap) : null;
  return <section id={`supplement-${item.requirementId}`} className="panel space-y-3 scroll-mt-24">
    <div className="min-w-0">
      <h3 className="break-words text-lg font-semibold">{item.skill || "岗位要求"} · {workspaceStatusLabel(item)}</h3>
      <p className="mt-1 break-words text-sm leading-6 text-slate-700">{item.requirementTitle}</p>
      <p className="mt-1 text-xs leading-5 text-slate-500">本项补证与岗位对照中的当前要求一致。</p>
    </div>
    <div className="space-y-3 border-t border-slate-200 pt-3">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h4 className="font-semibold text-slate-900">{action || plan ? "本项已保存的具体要求" : "以下为通用补证建议"}</h4>
        {action && ACTION_SOURCE_LABELS[action.source] && <span className="text-sm text-slate-600">{ACTION_SOURCE_LABELS[action.source]}</span>}
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
          <ol className="list-decimal space-y-2 pl-5">{followUpGuidance(report, item).steps.map((step, index) => <li key={index}>{step}</li>)}</ol>
          <p className="font-medium text-slate-800">建议提交的材料</p>
          <p className="text-xs leading-6 text-slate-600">以下为通用补证建议，按实际改进选择，不表示系统确认文件已经存在。</p>
          <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-slate-600"><li>与本项要求对应的源码及关键位置。</li><li>如本项要求涉及可执行验证，再提供相关测试文件、复现命令和执行记录；上传材料不等于平台已运行通过。</li><li>仅在多人协作时补充个人贡献说明。已有材料先定位，不必重复提交；运行结果与本人贡献分别核验。</li></ul>
        </div></details>
      </div>}
      {action && (text?.gap || (plan && text?.advice)) ? <details className="text-sm leading-7"><summary className="disclosure">报告补充说明</summary>
        {plan && text?.advice && <p className="whitespace-pre-wrap break-words">{text.advice}</p>}
        {text?.gap && <p className="whitespace-pre-wrap break-words text-slate-600">{text.gap}</p>}
      </details> : null}
    </div>
    <div id={`growth-${item.requirementId}`} className="scroll-mt-24">
      <ReportFollowUpActions reportId={report.id} requirementId={item.requirementId} projectVersionId={projectVersionId} text={followUpCopyText(report, item)} />
    </div>
  </section>;
}
