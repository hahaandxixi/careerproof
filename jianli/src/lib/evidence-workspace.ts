import type { MatchReport, ReportItem } from "./api/domain.ts";

// Match the saved plan's ordering without inheriting its three-item limit.
function prioritize(items: ReportItem[]) {
  return items.slice().sort((a, b) => b.weight - a.weight || (a.evidenceLevel ?? 0) - (b.evidenceLevel ?? 0));
}

export const ACTION_SOURCE_LABELS = {
  ai_suggestion: "AI 证据建议",
  rules: "本地规则提示",
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

export function evidenceWorkspace(items: ReportItem[]) {
  const supported = items.filter(item => ["supported", "verified"].includes(item.verdict) && !["rejected", "corrected"].includes(item.confirmationStatus ?? ""));
  const partial = items.filter(item => item.verdict === "partial" && !["rejected", "corrected"].includes(item.confirmationStatus ?? ""));
  const gaps = items.filter(item => ["gap", "claimed_only"].includes(item.verdict) && !["rejected", "corrected"].includes(item.confirmationStatus ?? ""));
  const other = items.filter(item => !supported.includes(item) && !partial.includes(item) && !gaps.includes(item));
  // Equal weight and level retain report order; never calculate an ability score.
  const priorities = prioritize(items.filter(item => gaps.includes(item) || partial.includes(item)));
  return { supported: prioritize(supported), partial: prioritize(partial), gaps: prioritize(gaps), other: prioritize(other), priorities };
}

export function evidenceWorkspaceSummary(items: ReportItem[]) {
  if (!items.length) return "这份报告尚无逐项要求，暂不能概括材料支持状态。";
  const state = evidenceWorkspace(items);
  const counts = `${items.length} 项要求：${state.supported.length} 项有证据支持、${state.partial.length} 项部分支持、${state.gaps.length} 项待补材料、${state.other.length} 项未覆盖或需复核。`;
  const first = state.priorities[0];
  return first ? `${counts}按岗位权重，先补「${first.requirementTitle}」的材料缺口。` : counts;
}
