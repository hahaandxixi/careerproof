import type { MatchReport } from "./api/domain";

const AI_MODES = new Set(["ai_evidence", "ai_evidence_manual"]);

export function reportReadingStatus(report: Pick<MatchReport, "analysisMode" | "aiFallbackUsed"> & {
  aiProvider?: string | null; aiProcess?: MatchReport["aiProcess"]; items?: MatchReport["items"];
}) {
  if (report.aiProvider?.startsWith("mock")) return { label: "演示结果", reason: "本报告未调用真实 AI。" };
  const hasRulesResult = !!report.items?.length;
  if (report.aiFallbackUsed) {
    const validationFailure = /invalid_output|output_token_limit|validation/i.test(report.aiProcess?.fallbackReason ?? "");
    if (!hasRulesResult) return { label: validationFailure ? "AI 结果未通过校验" : "暂无可用分析结果", reason: "没有可读取的分析结果。" };
    return { label: validationFailure ? "AI 结果未通过校验" : "AI 分析未完成", reason: "当前显示规则分析结果。" };
  }
  if (!AI_MODES.has(report.analysisMode)) return { label: "规则分析结果", reason: "本次未调用 AI 分析。" };
  const validated = report.items?.some(item => item.aiStatus === "validated") ?? false;
  if (validated) return { label: "AI 分析完成", reason: "引用和判断可逐项核对，不代表能力认证。" };
  return hasRulesResult
    ? { label: "规则分析结果", reason: "AI 未返回可保存并读取的校验结果，当前显示规则分析结果。" }
    : { label: "暂无可用分析结果", reason: "没有可读取的分析结果。" };
}

/** User-facing summary of a saved per-item AI status. */
export function aiStatusLabel(status: string | null | undefined): string {
  if (!status) return "未记录";
  if (status === "validated") return "AI 分析完成";
  if (/invalid|validation|failed/i.test(status)) return "AI 结果未通过校验";
  if (["rules_only", "not_used", "not_requested", "skipped"].includes(status)) return "规则分析结果";
  return "AI 分析未完成";
}

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
  if (report.aiFallbackUsed) return "规则证据报告";
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
