import type { ReportItem } from "./api/domain";

export function invalidNarrativeCitations(item: Pick<ReportItem, "aiExplanation" | "aiInformationGap" | "aiSuggestion" | "aiCitationIds" | "evidenceList">): string[] {
  const allowed = new Set((item.evidenceList??[]).map(e => e.citationId).filter(Boolean));
  const ids=item.aiCitationIds??[];
  const structured = new Set(ids);
  const found = [item.aiExplanation, item.aiInformationGap, item.aiSuggestion].join(" ").match(/\bR\d+-E\d+\b/g) ?? [];
  return [...new Set([...found, ...ids].filter(id => !allowed.has(id) || !structured.has(id)))];
}

export function readableCitationText(item: ReportItem, text: string): string {
  return text.replace(/\bR\d+-E\d+\b/g,id=>{
    const source=(item.aiCitationIds??[]).includes(id)?item.evidenceList.find(e=>e.citationId===id):null;
    return source?`${source.filePath.split(/[\\/]/).at(-1)} 第${source.lineStart}–${source.lineEnd}行`:id;
  });
}
