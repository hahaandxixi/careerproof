import type { GrowthPlan, MatchReport, ReportItem } from "./api/domain";

const EXTERNAL_AI_PROVIDERS = new Set(["deepseek", "bailian", "qianwen", "zhipu"]);

export function taskUsedExternalAI(provider: unknown, fallbackUsed: unknown) {
  return EXTERNAL_AI_PROVIDERS.has(String(provider)) && fallbackUsed !== true;
}

export function sourceContextVerified(version: string | null | undefined) {
  return /^source-context-v(?:[2-9]|\d{2,})(?:-|$)/.test(version ?? "");
}

export interface GrowthAdviceDraft {
  suggestion: string;
  gap: string;
  citationIds: string[];
  suggestedKind: GrowthPlan["gapKind"];
  taskPlan: Pick<GrowthPlan, "deliverable" | "steps" | "acceptanceChecks"> | null;
}

export interface EditableGrowthDraft {
  kind: GrowthPlan["gapKind"];
  kindEdited: boolean;
  deliverable: string;
  steps: string;
  checks: string;
}

export function adoptGrowthAdvice(current: EditableGrowthDraft, advice: GrowthAdviceDraft): EditableGrowthDraft {
  return {
    ...current,
    kind: current.kindEdited ? current.kind : advice.suggestedKind,
    deliverable: current.deliverable.trim() ? current.deliverable : advice.taskPlan?.deliverable || advice.suggestion,
    steps: current.steps.trim() ? current.steps : advice.taskPlan?.steps.join("\n") || current.steps,
    checks: current.checks.trim() ? current.checks : advice.taskPlan?.acceptanceChecks.join("\n") || current.checks,
  };
}

function usableTaskPlan(value: ReportItem["aiTaskPlan"]): GrowthAdviceDraft["taskPlan"] {
  if (!value || typeof value.deliverable !== "string" || !value.deliverable.trim()
    || value.deliverable.length > 200) return null;
  const lines = (input: unknown) => Array.isArray(input) && input.length >= 1 && input.length <= 3
    && input.every(line => typeof line === "string" && !!line.trim() && line.length <= 200)
    ? input.map(line => line.trim()) as string[] : null;
  const steps = lines(value.steps);
  const acceptanceChecks = lines(value.acceptanceChecks);
  return steps && acceptanceChecks
    ? { deliverable: value.deliverable.trim(), steps, acceptanceChecks } : null;
}

function suggestedGapKind(gap: string): GrowthPlan["gapKind"] {
  if (/(?:未|尚未|没有|缺少|无)[^，。；,;]{0,24}(?:实现|调用|读写逻辑|读写代码)/.test(gap)) return "implementation";
  if (/运行|测试(?:执行|结果|输出)|响应记录|日志/.test(gap)) return "execution";
  if (/本人贡献|代码归属|提交记录/.test(gap)) return "contribution";
  return "implementation";
}

export function validatedGrowthAdvice(report: MatchReport, item: ReportItem): GrowthAdviceDraft | null {
  if (report.aiFallbackUsed || !sourceContextVerified(report.evidenceContextVersion)
    || item.aiStatus !== "validated"
    || item.aiSuggestionRedundant
    || item.confirmationStatus === "rejected"
    || item.confirmationStatus === "corrected") return null;
  const suggestion = item.aiSuggestion?.trim();
  if (!suggestion || suggestion.length > 1000) return null;
  const allowed = new Set(item.evidenceList.map(source => source.citationId).filter(Boolean));
  if (item.aiCitationIds.some(id => !allowed.has(id))
    || new Set(item.aiCitationIds).size !== item.aiCitationIds.length) return null;
  if (["supported", "partial"].includes(item.verdict) && item.evidenceList.length && !item.aiCitationIds.length) return null;
  const gap = item.aiInformationGap?.trim() || item.evidenceLevelGap?.trim() || "请核对本要求未证实的部分。";
  return {
    suggestion,
    gap,
    citationIds: [...item.aiCitationIds],
    suggestedKind: suggestedGapKind(gap),
    taskPlan: item.aiTaskPlanWarning ? null : usableTaskPlan(item.aiTaskPlan),
  };
}
