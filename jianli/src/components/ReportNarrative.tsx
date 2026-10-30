import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { compactSourceLabel } from "@/lib/source-label";
import EvidenceLink from "./EvidenceLink";

/** Display aliases as source links; keep saved model text untouched in storage. */
export default function ReportNarrative({text,item,report,sourcePrefix=""}:{text:string;item:ReportItem;report:MatchReport;sourcePrefix?:string}) {
  return <>{text.split(/(\bR\d+-E\d+\b)/g).map((part,i)=>{
    const source=item.aiCitationIds.includes(part)?item.evidenceList.find(e=>e.citationId===part):null;
    return source ? <EvidenceLink key={i} targetId={`${sourcePrefix}citation-${part}`} className="text-indigo-800 underline underline-offset-2">{compactSourceLabel(source,report.materials).fileName} · {source.lineStart}–{source.lineEnd}行</EvidenceLink> : part;
  })}</>;
}
