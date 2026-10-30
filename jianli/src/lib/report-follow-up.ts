import type { GrowthPlan, MatchReport, ReportItem } from "./api/domain";
import { validatedGrowthAdvice } from "./analysis-status";
import { ACTION_SOURCE_LABELS, evidenceWorkspace } from "./evidence-workspace";
import { requirementConclusion, savedRequirementAction, workspaceStatusLabel } from "./report-workspace";

export type FollowUpPlan = Pick<GrowthPlan, "deliverable" | "steps" | "acceptanceChecks">;

// Shared UI/copy instructions, never generated implementation claims or saved task data.
export const GENERAL_FOLLOW_UP = [
  "检查已有实现：对照岗位要求，在自己的项目中核对相关业务代码与测试。未检索到引用不代表没有实现。",
  "已有实现：整理对应文件、关键行和相关测试；如有运行记录，注明对应源码版本与执行范围。已提交的材料只需定位，不必重复上传。",
  "尚未实现：先确认实际缺口，再在自己的开发环境完善相关代码与行为测试；未运行的测试要明确标注，不作为成功结果。",
  "提交新版材料：确有新增时上传工程或验证材料，在岗位页明确选择版本并主动生成新报告；比较引用和逐项解释，等级不一定变化。",
] as const;
export const REVIEW_FOLLOW_UP = [
  "对照岗位原文与已有来源，核对规则覆盖范围和本人复核意见；不能由此认定实现不存在。",
  "记录仍不确定的部分与需要人工核对的材料位置，再决定是否补充新版材料。",
] as const;

export function followUpGuidance(report: MatchReport, item: ReportItem, savedPlan?: FollowUpPlan | null) {
  const advice = validatedGrowthAdvice(report, item);
  const action = savedRequirementAction(report, item);
  const plan = savedPlan ?? advice?.taskPlan;
  const state = evidenceWorkspace([item]);
  const actionable = state.gaps.length + state.partial.length > 0;
  return {
    gap: advice?.gap || item.evidenceLevelGap?.trim() || action?.evidenceGap?.trim() || requirementConclusion(item),
    action, plan,
    steps: plan?.steps ?? (actionable ? GENERAL_FOLLOW_UP : REVIEW_FOLLOW_UP),
  };
}

export function followUpCopyText(report: MatchReport, item: ReportItem, savedPlan?: FollowUpPlan | null): string {
  const { gap, action, plan, steps } = followUpGuidance(report, item, savedPlan);
  return [
    `岗位：${report.jobTitle || "本报告岗位"}`,
    `岗位要求：${item.requirementTitle}`,
    `材料支持状态：${workspaceStatusLabel(item)}`,
    `当前证据缺口/待核对：${gap || "尚无保存说明，请核对来源。"}`,
    action ? `已保存补证建议（${ACTION_SOURCE_LABELS[action.source]}）：${action.action}` : "本报告没有可采用的已保存补证建议。",
    plan ? "已保存计划（仍需本人核对，不代表已执行）：" : "通用核对步骤（操作提示，不是 AI 分析结果或实现事实）：",
    ...steps.map((step, index) => `${index + 1}. ${step}`),
    ...(plan ? [`建议提交的证据：${plan.deliverable}`, "核验条件：", ...plan.acceptanceChecks.map(check => `- ${check}`)] : []),
    "提醒：已有材料先核对位置，确有新增再上传；用户提供的运行记录不等于平台独立执行，也不能单独证明本人贡献。",
    ...(item.evidenceList.some(source => source.contextComplete === false) ? ["部分引用上下文不完整，须核对原始来源。"] : []),
    ...(item.aiTaskPlanWarning ? [`任务草稿待核对：${item.aiTaskPlanWarning}`] : []),
    "不必创建补证记录。在外部完善材料后，明确选择新版并主动分析；旧报告和企业投递快照保持不变。",
  ].join("\n\n");
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function reportFollowUpContext(query: Pick<URLSearchParams, "get">) {
  const reportId = query.get("sourceReport"), requirementId = query.get("sourceRequirement");
  return reportId && requirementId && UUID.test(reportId) && UUID.test(requirementId) ? { reportId, requirementId } : null;
}

/** These parameters are navigation hints only; the receiver checks the owned report. */
export function reportUploadHref(reportId: string, requirementId: string, projectVersionId?: string): string {
  return UUID.test(reportId) && UUID.test(requirementId)
    ? `/portfolio?${new URLSearchParams({ sourceReport: reportId, sourceRequirement: requirementId, add:"project", ...(projectVersionId && UUID.test(projectVersionId) ? {sourceProjectVersion:projectVersionId}: {}) })}` : "/portfolio";
}
