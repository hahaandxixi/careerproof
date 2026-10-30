import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { adoptedReportExplanation } from "@/lib/report-workspace";
import { compactSourceLabel, sourceLocationId } from "@/lib/source-label";
import EvidenceSnippet from "./EvidenceSnippet";
import { SourceIdentityDetails } from "./SourceIdentity";
import { sourceLimit } from "@/lib/source-limits";

export default function ReportSourcePanel({ report, item }: { report: MatchReport; item: ReportItem }) {
  const adopted = !!adoptedReportExplanation(report, item);
  const first = adopted ? item.evidenceList.findIndex(source => !!source.citationId && item.aiCitationIds.includes(source.citationId)) : 0;
  return <section className="min-w-0" aria-label={`${item.skill}的证据来源`}>
    <h4 className="font-semibold">来源</h4>
    {item.evidenceList.length ? <div className="mt-3 space-y-2">{item.evidenceList.map((source, index) => {
      const label = compactSourceLabel(source, report.materials);
      const limit = sourceLimit(report, source);
      return <details key={`${source.filePath}-${index}`} open={index === Math.max(0, first)} className="rounded-lg border border-slate-200 open:border-indigo-300">
        <summary className="cursor-pointer p-3 text-base text-indigo-900"><strong>{label.fileName}</strong><span className="ml-2 text-sm">第 {source.lineStart}–{source.lineEnd} 行</span>{limit && <span className="ml-2 text-sm text-amber-900">{limit.label}</span>}<span className="mt-1 block text-sm text-slate-600">{label.material}{source.provenance === "reference" ? " · 第三方参考，不计评级" : ""}</span></summary>
        <div id={sourceLocationId(item.requirementId, source, index)} className="min-w-0 scroll-mt-24 px-3 pb-3">
          {limit && <p className="mb-2 text-sm leading-6 text-amber-900">{limit.detail}</p>}
          {limit?.readable !== false && <EvidenceSnippet evidence={source} materials={report.materials} showContextNote={false} />}
          <details className="mt-2 text-sm text-slate-600"><summary className="cursor-pointer py-1">来源说明</summary><p className="mt-2 break-words leading-6">{source.explanation}</p><p className="mt-2">{source.citationId || `规则来源 ${index + 1}`} · {source.contextNote}</p></details>
          <SourceIdentityDetails source={source} />
        </div>
      </details>;
    })}</div> : <p className="mt-3 text-sm leading-7 text-slate-600">{item.verdict === "unsupported" ? "当前规则未覆盖此要求，请人工核对保存材料。" : "当前报告没有对应的可定位引用，不能据此认定没有这项能力。"}</p>}
  </section>;
}
