import type { MatchReport, ReportItem } from "./api/domain.ts";
import { validatedGrowthAdvice } from "./analysis-status";
import { evidenceWorkspace } from "./evidence-workspace";
import { VERDICT_LABELS } from "./verdict-display.js";

export type WorkspaceFilter = "priority" | "all" | "supported" | "partial" | "gaps" | "other";

/** Reading filters project saved states; they never change a verdict or material. */
export function workspaceRequirements(items: ReportItem[], filter: WorkspaceFilter): ReportItem[] {
  if (filter === "all") return items;
  const state = evidenceWorkspace(items);
  return filter === "priority" ? [...state.priorities, ...state.other] : state[filter];
}

export function initialWorkspaceFilter(items: ReportItem[]): WorkspaceFilter {
  return workspaceRequirements(items, "priority").length ? "priority" : "all";
}

export function filterForRequirement(items: ReportItem[], filter: WorkspaceFilter, id: string): WorkspaceFilter {
  return workspaceRequirements(items, filter).some(item => item.requirementId === id) ? filter : "all";
}

export function workspaceStatusLabel(item: ReportItem): string {
  if (item.confirmationStatus === "rejected") return "本人已驳回 · 需复核";
  if (item.confirmationStatus === "corrected") return "本人标记修正 · 需复核";
  return VERDICT_LABELS[item.verdict] ?? item.verdict;
}

/** Keep raw technical explanations intact in the evidence reader, not in the scan list. */
export function requirementConclusion(item: ReportItem): string {
  const technical = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f-]{20,}|[\\/][^\s，。；]+\.(?:py|tsx?|jsx?|sql|json|txt)\b|本项静态引用/i;
  const candidates = [item.explanation, item.evidenceLevelReason].map(text => text?.trim()).filter(Boolean) as string[];
  const concise = candidates.find(text => !technical.test(text));
  if (concise) return concise;
  return `${workspaceStatusLabel(item)}；本报告保存了 ${item.evidenceList.length} 条来源，可展开核对判断范围。`;
}

export function requirementSummary(item: ReportItem): string {
  const text = requirementConclusion(item);
  return text.length > 90 ? `${text.slice(0, 90)}…` : text;
}

/** Action-plan entries are bounded suggestions, not another list of requirements. */
export function savedRequirementAction(report: MatchReport, item: ReportItem) {
  const action = report.actionPlan?.find(value => value.requirementId === item.requirementId);
  if (!action) return null;
  if (action.source === "ai_suggestion" && !validatedGrowthAdvice(report, item)) return null;
  if (!["rules", "review", "ai_suggestion"].includes(action.source)) return null;
  return action;
}

/** Visibility only: saved ratings and explanations are never recomputed. */
export function adoptedReportExplanation(report: MatchReport, item: ReportItem): string | null {
  if (!["ai_evidence", "ai_evidence_manual"].includes(report.analysisMode)
    || report.aiProvider?.startsWith("mock") || report.aiFallbackUsed
    || item.aiStatus !== "validated"
    || ["rejected", "corrected"].includes(item.confirmationStatus ?? "")) return null;
  return item.aiExplanation?.trim() || null;
}
