import type { MatchReport, ReportEvidence, ReportItem } from "./api/domain";
import { sourceContextVerified } from "./analysis-status";

export function sourceLimit(report: MatchReport, source: ReportEvidence): { label: string; detail: string; readable: boolean } | null {
  if (source.projectVersionId && !report.materials.some(m => m.id === source.projectVersionId))
    return { label: "不在本报告材料范围", detail: "不能展示未包含在固定材料清单中的来源；请核对原报告授权与版本。", readable: false };
  if (!source.snippet?.trim() || source.lineStart < 1 || source.lineEnd < source.lineStart)
    return { label: "来源暂不可读", detail: "本条引用缺少可读取原文或有效定位，请核对历史材料；不会跳转到最新版本替代。", readable: false };
  if (!sourceContextVerified(report.evidenceContextVersion))
    return { label: "历史完整性信息不足", detail: "保留当时来源，尚不能确认完整上下文；请核对原始版本。", readable: true };
  if (source.contextComplete === false)
    return { label: "局部原文", detail: "此处仅展示局部原文，不表示整个函数或项目缺失；可核对本要求的其他来源。", readable: true };
  return null;
}

export function unsentRuleSources(item: ReportItem) {
  return item.evidenceList.map((source,index)=>({source,index})).filter(({source})=>!source.citationId);
}

export function historicalScopeOnly(item: ReportItem) {
  return /规则层保存了未发送证据/.test(item.aiInformationGap ?? "");
}
