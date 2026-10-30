import type { MatchReport, ReportEvidence } from "@/lib/api/domain";
import { agentEvidenceRows, agentProcessSummary } from "@/lib/agent-evidence";
import { validatedGrowthAdvice } from "@/lib/analysis-status";
import EvidenceLink from "./EvidenceLink";
import EvidenceSnippet from "./EvidenceSnippet";
import SourceIdentity, { SourceIdentityDetails } from "./SourceIdentity";

function Source({ evidence, report }: { evidence: ReportEvidence; report: MatchReport }) {
  return <div className="min-w-0 rounded-lg border border-slate-200 bg-white p-3">
    <p className="break-all text-xs leading-6 text-slate-700"><SourceIdentity source={evidence} materials={report.materials} /> · 第 {evidence.lineStart}—{evidence.lineEnd} 行</p>
    <EvidenceSnippet evidence={evidence} materials={report.materials} />
    <SourceIdentityDetails source={evidence} />
    {evidence.citationId && <EvidenceLink citationId={evidence.citationId} className="mt-2 inline-block text-sm text-indigo-700 underline">定位完整引用 {evidence.citationId} →</EvidenceLink>}
  </div>;
}

export default function ReportAgentEvidence({ report, canGrow }: { report: MatchReport; canGrow: boolean }) {
  const rows = agentEvidenceRows(report);
  if (!rows.length) return null;
  const mock = report.aiProvider?.startsWith("mock") === true;
  return <details className="min-w-0 space-y-3 border-t border-slate-200 pt-2">
    <summary id="agent-evidence-title" className="disclosure">检索记录（{rows.length}）</summary>
    {mock && <p className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm font-medium text-indigo-950">Mock 界面验证：材料与片段可核对，工具选择和模型输出为预设，不是真实模型运行证据。</p>}
    <p className="text-sm leading-7 text-slate-700">{agentProcessSummary(report)}</p>
    {rows.map(({ call, item, added, otherSaved, action, influence }, index) => <article key={index} className="min-w-0 space-y-3 rounded-xl border border-indigo-100 bg-indigo-50/30 p-4">
      <h3 className="break-words font-semibold text-slate-900">{item?.requirementTitle ?? "本次分析的工具记录"}</h3>
      {call.query && <p className="break-words text-sm leading-7 text-slate-700"><strong>本轮待核对的问题：</strong>{call.query}（来自已保存的工具请求，不是初始判断）</p>}
      <p className="text-sm leading-7 text-slate-700"><strong>实际动作：</strong>{action}</p>
      {added && <div><p className="mb-2 text-sm font-medium text-indigo-950">补充找到的证据</p><Source evidence={added} report={report} /></div>}
      {added && otherSaved.length > 0 && <details className="rounded-lg border border-slate-200 bg-white p-3"><summary className="cursor-pointer text-sm font-medium text-slate-700">对照其他已保存引用 · {otherSaved.length} 条</summary><p className="mt-2 text-xs leading-6 text-slate-600">这里排除本轮记录的新增编号；没有保存补检索前的完整输入，不能据此还原首轮实际发送了哪些片段。</p><div className="mt-3 space-y-3">{otherSaved.map(evidence => <Source key={evidence.citationId} evidence={evidence} report={report} />)}</div></details>}
      <p className="text-sm leading-7 text-slate-700"><strong>结论中的作用：</strong>{influence}</p>
      {item && <><p className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-700"><strong>最终保存的解释：</strong>{item.aiStatus === "validated" && !report.aiFallbackUsed ? item.aiExplanation || item.explanation : item.explanation}</p>
        <p className="break-words text-sm leading-7 text-slate-700"><strong>当前仍待确认：</strong>{item.aiStatus === "validated" && !report.aiFallbackUsed ? item.aiInformationGap || item.evidenceLevelGap : item.evidenceLevelGap || "请核对逐项缺口。"}</p>
        {validatedGrowthAdvice(report, item)?.suggestion && <p className="break-words text-sm leading-7 text-slate-700"><strong>下一步建议：</strong>{validatedGrowthAdvice(report, item)?.suggestion}</p>}
        <div className="flex flex-wrap gap-4 text-sm"><a href={`#requirement-${item.requirementId}`} className="text-indigo-700 underline">核对完整要求与结论 →</a>{canGrow && <a href={`#growth-${item.requirementId}`} className="font-medium text-indigo-700 underline">从这条要求继续补证 →</a>}</div></>}
    </article>)}
    {canGrow && !rows.some(row => row.item) && <a className="inline-block text-sm font-medium text-indigo-700 underline" href="#evidence-workspace-title">核对报告缺口与补证计划 →</a>}
    <details className="text-xs text-slate-600"><summary className="cursor-pointer">技术记录与范围</summary><ul className="mt-2 space-y-2">{rows.map(({ call }, index) => <li key={index} className="break-all">{call.tool} · {call.status ?? "未保存状态"} · {call.scope ?? "未保存范围"}{call.round ? ` · 第${call.round}轮` : ""}</li>)}</ul></details>
  </details>;
}
