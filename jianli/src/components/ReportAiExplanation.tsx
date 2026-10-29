import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { adoptedReportExplanation } from "@/lib/report-workspace";
import EvidenceLink from "./EvidenceLink";
import { sourceContextVerified } from "@/lib/analysis-status";
import { compactSourceLabel } from "@/lib/source-label";

/** Project the accepted, saved explanation; never infer a new model result. */
export default function ReportAiExplanation({ report, item }: { report: MatchReport; item: ReportItem }) {
  const explanation = adoptedReportExplanation(report, item);
  if (!explanation) return null;
  return <section className="rounded-xl border-l-4 border-indigo-500 bg-indigo-50/60 p-4" aria-label={`${item.skill}的AI证据解释`}>
    <h4 className="font-semibold text-indigo-950">AI 解释</h4>
    <p className="mt-2 whitespace-pre-wrap break-words text-base leading-7 text-slate-900">{explanation}</p>
    <div className="mt-3 flex flex-wrap gap-2">{item.aiCitationIds.map(citation => {
      const source = item.evidenceList.find(value => value.citationId === citation);
      return <EvidenceLink key={citation} citationId={citation} className="inline-flex min-h-10 items-center rounded-lg border border-indigo-200 bg-white px-3 text-sm text-indigo-800">{source ? `${compactSourceLabel(source, report.materials).fileName} · ${source.lineStart}–${source.lineEnd}行` : `查看来源 ${citation}`}</EvidenceLink>;
    })}</div>
    <details className="mt-2 text-sm text-slate-600"><summary className="cursor-pointer py-1">解释范围与已保存建议原文</summary>
      <p className="mt-2">{sourceContextVerified(report.evidenceContextVersion) ? "引用与原文已通过本报告校验，解释是否充分仍需核对。" : "历史解释仅保留当时校验结果，未通过当前完整上下文检查。"}不证明代码运行成功或本人贡献。</p>
      {item.aiConfidence != null && <p className="mt-2">解释置信度 {Math.round(item.aiConfidence * 100)}%</p>}
      {item.aiInformationGap && <p className="mt-2 whitespace-pre-wrap break-words">仍缺少：{item.aiInformationGap}</p>}
      {item.aiSuggestion && <p className="mt-2 whitespace-pre-wrap break-words">建议补充：{item.aiSuggestion}</p>}
      {item.aiSuggestionRedundant && <p className="mt-2 text-amber-900">这条旧建议重复要求当前已有的源码，仅保留原文，不用于补证草稿。</p>}
    </details>
  </section>;
}
