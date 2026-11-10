import type { MatchReport } from "./api/domain";

const AI_MODES = new Set(["ai_evidence", "ai_evidence_manual"]);

export function reportReadingStatus(report: Pick<MatchReport, "analysisMode" | "aiFallbackUsed"> & {
  aiProvider?: string | null; aiProcess?: MatchReport["aiProcess"]; items?: MatchReport["items"];
}): { label: string; reason: string } | null {
  if (report.aiProvider?.startsWith("mock")) return { label: "演示结果", reason: "本报告未调用真实 AI。" };
  const hasRulesResult = !!report.items?.length;
  if (report.aiFallbackUsed) {
    const validationFailure = /invalid_output|output_token_limit|validation/i.test(report.aiProcess?.fallbackReason ?? "");
    if (!hasRulesResult) return { label: validationFailure ? "AI 结果未通过校验" : "暂无可用分析结果", reason: "没有可读取的分析结果。" };
    // A fallback is a rules result: surface the real failure state only, never a source label.
    return { label: validationFailure ? "AI 结果未通过校验" : "AI 分析未完成", reason: "" };
  }
  // A plain rules result carries no reading-status notice at all.
  if (!AI_MODES.has(report.analysisMode)) return null;
  const validated = report.items?.some(item => item.aiStatus === "validated") ?? false;
  if (validated) return { label: "AI 分析完成", reason: "" };
  return hasRulesResult
    ? { label: "AI 分析未完成", reason: "" }
    : { label: "暂无可用分析结果", reason: "没有可读取的分析结果。" };
}

/** User-facing summary of a saved per-item AI status. */
export function aiStatusLabel(status: string | null | undefined): string {
  if (!status) return "未记录";
  if (status === "validated") return "AI 分析完成";
  if (/invalid|validation|failed/i.test(status)) return "AI 结果未通过校验";
  if (["rules_only", "not_used", "not_requested", "skipped"].includes(status)) return "未采用 AI";
  return "AI 分析未完成";
}

/** Count only the items that actually received an AI preliminary rating. */
export function reportAiRatedCount(report: Pick<MatchReport, "items">): number {
  return report.items.filter(item => item.evidenceLevelSource === "ai_preliminary").length;
}

/**
 * One label for the same saved report on both student and enterprise surfaces.
 * A fallback is a rules result even when the configured provider was external AI,
 * so it renders no analysis badge. The badge appears only for genuinely valid AI
 * results: no mock provider, no fallback, an AI mode, and a validated or AI-rated
 * item actually saved. Empty string means "render nothing".
 */
export function reportModeLabel(
  report: Pick<MatchReport, "analysisMode" | "aiFallbackUsed" | "items"> & { aiProvider?: string | null },
): string {
  if (report.aiProvider?.startsWith("mock")) return "演示结果";
  if (report.aiFallbackUsed || !AI_MODES.has(report.analysisMode)) return "";
  const validated = report.items?.some(item => item.aiStatus === "validated") ?? false;
  return validated || reportAiRatedCount(report) > 0 ? "AI 分析" : "";
}

/** Historical summaries keep their facts; only the displayed rating wording is aligned. */
export function reportSummaryText(summary: string): string {
  return summary
    .replace("分数为材料支持度，不是能力或录用结论。", "评级描述材料证据，不是能力或录用结论。")
    .replace("暂不支持评估且不计分", "暂不支持评估且不评级");
}
