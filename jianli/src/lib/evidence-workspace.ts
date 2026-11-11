import type { MatchReport, ReportItem } from "./api/domain.ts";

// Match the saved plan's ordering without inheriting its three-item limit.
function prioritize(items: ReportItem[]) {
  return items.slice().sort((a, b) => b.weight - a.weight || (a.evidenceLevel ?? 0) - (b.evidenceLevel ?? 0));
}

export const ACTION_SOURCE_LABELS = {
  ai_suggestion: "AI 证据建议",
  rules: "",
  review: "人工复核后",
} as const;

const normalized = (text?: string | null) => text?.trim().replace(/\s+/g, " ") ?? "";

/** Present distinct saved text, never manufacture new advice. */
export function distinctActionText(action: MatchReport["actionPlan"][number], displayedGap?: string) {
  const advice = action.action?.trim() ?? "";
  const gap = action.evidenceGap?.trim() ?? "";
  return {
    advice: normalized(advice) === normalized(displayedGap) ? "" : advice,
    gap: [normalized(advice), normalized(displayedGap)].includes(normalized(gap)) ? "" : gap,
  };
}

export function effectiveReportStatus(item: ReportItem) {
  if (item.confirmationStatus === "rejected" || item.confirmationStatus === "corrected") return item.confirmationStatus;
  switch (item.verdict) {
    case "verified": return "supported";
    case "not_evaluated": return "not_evaluated";
    case "supported": case "partial": case "gap": case "claimed_only": case "unsupported": return item.verdict;
    default: return "unknown";
  }
}

export function reportStatusTone(item: ReportItem) {
  const status = effectiveReportStatus(item);
  if (status === "supported" || status === "partial") return status;
  return status === "gap" || status === "claimed_only" ? "gap" : "other";
}

export function nextReportGap(gaps: ReportItem[], selected: string | null) {
  const index = gaps.findIndex(item => item.requirementId === selected);
  if (index < 0) return gaps[0];
  return gaps.length > 1 ? gaps[(index + 1) % gaps.length] : undefined;
}

export function evidenceWorkspace(items: ReportItem[]) {
  const groups: Record<"supported" | "partial" | "gap" | "other", ReportItem[]> = {
    supported: [], partial: [], gap: [], other: [],
  };
  for (const item of prioritize(items)) groups[reportStatusTone(item)].push(item);
  const { supported, partial, gap: gaps, other } = groups;
  const priorities = prioritize(items.filter(item => {
    const tone = reportStatusTone(item);
    return tone === "gap" || tone === "partial";
  }));
  return { supported, partial, gaps, other, priorities };
}

export function evidenceWorkspaceSummary(items: ReportItem[]) {
  if (!items.length) return "这份报告尚无逐项要求，暂不能概括材料支持状态。";
  const state = evidenceWorkspace(items);
  const counts = `${items.length} 项要求：${state.supported.length} 项有证据支持、${state.partial.length} 项部分支持、${state.gaps.length} 项待补材料、${state.other.length} 项未覆盖或需复核。`;
  const first = state.priorities[0];
  return first ? `${counts}按岗位权重，先补「${first.requirementTitle}」的材料缺口。` : counts;
}
