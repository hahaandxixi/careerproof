import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { adoptedReportExplanation } from "@/lib/report-workspace";
import EvidenceLink from "./EvidenceLink";
import { sourceContextVerified } from "@/lib/analysis-status";
import { compactSourceLabel } from "@/lib/source-label";
import { invalidNarrativeCitations } from "@/lib/report-citations";
import { historicalScopeOnly, unsentRuleSources } from "@/lib/source-limits";
import { sourceLocationId } from "@/lib/source-label";
import ReportNarrative from "./ReportNarrative";

/** Project the accepted, saved explanation; never infer a new model result. */
export default function ReportAiExplanation({ report, item }: { report: MatchReport; item: ReportItem }) {
  const explanation = adoptedReportExplanation(report, item);
  if (!explanation) return null;
  const invalid = invalidNarrativeCitations(item);
  const unsent = unsentRuleSources(item);
  if (invalid.length) return <section className="rounded-lg border border-amber-200 p-4 text-base leading-7" role="note">
    <p>这份历史解释含有未与本项来源对齐的引用，暂不能作为已核验解释。请核对下方固定来源。</p>
    <details className="mt-2"><summary className="cursor-pointer text-indigo-700">查看保存原文与异常编号</summary><p className="mt-2 whitespace-pre-wrap">{explanation}</p><p>{invalid.join("、")}</p>{item.aiInformationGap && <p>{item.aiInformationGap}</p>}{item.aiSuggestion && <p>{item.aiSuggestion}</p>}</details>
  </section>;
  return <section className="rounded-xl border-l-4 border-indigo-500 bg-indigo-50/60 p-4" aria-label={`${item.skill}的AI证据解释`}>
    <h4 className="font-semibold text-indigo-950">AI 解释</h4>
    <p className="mt-2 whitespace-pre-wrap break-words text-base leading-7 text-slate-900"><ReportNarrative text={explanation} item={item} report={report}/></p>
    {unsent.length>0 && <details className="mt-3 text-sm"><summary className="cursor-pointer text-amber-900">本次 AI 只分析了部分来源</summary><p className="mt-2">以下已保存材料未参与本次 AI 分析。请先核对，再判断对应缺口；它们不自动证明运行成功或本人贡献。</p><ul>{unsent.slice(0,3).map(({source,index})=><li key={index}><a className="inline-flex min-h-10 items-center text-indigo-700 underline" href={`#${sourceLocationId(item.requirementId,source,index)}`}>{compactSourceLabel(source,report.materials).fileName} · {source.lineStart}–{source.lineEnd}行</a></li>)}</ul>{unsent.length>3&&<p>其余来源可在右侧列表查看。</p>}</details>}
    {historicalScopeOnly(item)&&<p className="mt-3 text-sm text-amber-900">旧记录仅保存了分析范围提示，具体缺口原文无法恢复；请核对来源及现有建议，不据此断言整个项目缺失。</p>}
    <div className="mt-3 flex flex-wrap gap-2">{item.aiCitationIds.map(citation => {
      const source = item.evidenceList.find(value => value.citationId === citation);
      return <EvidenceLink key={citation} citationId={citation} className="inline-flex min-h-10 items-center rounded-lg border border-indigo-200 bg-white px-3 text-sm text-indigo-800">{source ? `${compactSourceLabel(source, report.materials).fileName} · ${source.lineStart}–${source.lineEnd}行` : `查看来源 ${citation}`}</EvidenceLink>;
    })}</div>
    <details className="mt-2 text-sm text-slate-600"><summary className="cursor-pointer py-1">原始解释与校验记录</summary>
      <p className="mt-2 whitespace-pre-wrap break-words">{explanation}</p>
      <p className="mt-2">{sourceContextVerified(report.evidenceContextVersion) ? "生成时记录了引用与原文校验，解释是否充分仍需核对。" : "历史解释仅保留当时校验结果，未通过当前完整上下文检查。"}</p>
      {item.aiConfidence != null && <p className="mt-2">解释置信度 {Math.round(item.aiConfidence * 100)}%</p>}
      {item.aiInformationGap && <p className="mt-2 whitespace-pre-wrap break-words">仍缺少：{item.aiInformationGap}</p>}
      {item.aiSuggestion && <p className="mt-2 whitespace-pre-wrap break-words">建议补充：{item.aiSuggestion}</p>}
      {item.aiSuggestionRedundant && <p className="mt-2 text-amber-900">这条旧建议重复要求当前已有的源码，仅保留原文，不用于补证草稿。</p>}
    </details>
  </section>;
}
