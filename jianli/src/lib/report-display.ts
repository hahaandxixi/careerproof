import type { MatchReport } from "./api/domain";

const AI_MODES = new Set(["ai_evidence", "ai_evidence_manual"]);

/** Count only the items that actually received an AI preliminary rating. */
export function reportAiRatedCount(report: Pick<MatchReport, "items">): number {
  return report.items.filter(item => item.evidenceLevelSource === "ai_preliminary").length;
}

/**
 * One label for the same saved report on both student and enterprise surfaces.
 * A fallback is a rules result even when the configured provider was external AI.
 */
export function reportModeLabel(
  report: Pick<MatchReport, "analysisMode" | "aiFallbackUsed" | "items"> & { aiProvider?: string | null },
): string {
  if (report.aiProvider?.startsWith("mock")) return "Mock 界面验证 · 非真实模型报告";
  if (report.aiFallbackUsed) return "规则报告 · 模型已降级";
  if (report.analysisMode === "rules") return "规则证据报告";
  if (!AI_MODES.has(report.analysisMode)) return "未知报告模式";
  return reportAiRatedCount(report) > 0 ? "AI 证据初评 + 规则校验" : "规则证据 + AI 解释";
}

/** Historical summaries keep their facts; only the displayed rating wording is aligned. */
export function reportSummaryText(summary: string): string {
  return summary
    .replace("分数为材料支持度，不是能力或录用结论。", "评级描述材料证据，不是能力或录用结论。")
    .replace("暂不支持评估且不计分", "暂不支持评估且不评级");
}
