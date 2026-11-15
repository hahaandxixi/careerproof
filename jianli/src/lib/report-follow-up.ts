import type { GrowthPlan, MatchReport, ReportItem } from "./api/domain";
import { validatedGrowthAdvice } from "./analysis-status";
import { ACTION_SOURCE_LABELS, distinctActionText } from "./evidence-workspace";
import { requirementConclusion, savedRequirementAction, workspaceStatusLabel } from "./report-workspace";
import { displayJobTitle } from "./demo-display-identity.js";

type FollowUpPlan = Pick<GrowthPlan, "deliverable" | "steps" | "acceptanceChecks">;

export function supplementPlanLines(plan: FollowUpPlan) {
  const steps = plan.steps.filter(step => step.trim());
  const checks = plan.acceptanceChecks.filter(check => check.trim());
  return [
    ...(plan.deliverable.trim() ? [`提交什么：${plan.deliverable.trim()}`] : []),
    ...(steps.length ? ["执行步骤：", ...steps.map((step, index) => `${index + 1}. ${step}`)] : []),
    ...(checks.length ? ["核对项：", ...checks.map(check => `- ${check}`)] : []),
  ];
}

export function followUpGuidance(report: MatchReport, item: ReportItem) {
  const advice = validatedGrowthAdvice(report, item);
  const action = savedRequirementAction(report, item);
  const gap = advice?.gap || item.evidenceLevelGap?.trim() || action?.evidenceGap?.trim() || requirementConclusion(item);
  const plan = advice?.taskPlan;
  const text = action ? distinctActionText(action, gap) : null;
  if (plan && text) {
    const normalize = (value: string) => value.trim().replace(/\s+/g, " ");
    const displayed = new Set([plan.deliverable, ...plan.steps, ...plan.acceptanceChecks].map(normalize));
    if (displayed.has(normalize(text.advice))) text.advice = "";
    if (displayed.has(normalize(text.gap))) text.gap = "";
  }
  return { gap, action, plan, text };
}

export function followUpCopyText(report: MatchReport, item: ReportItem, guidance = followUpGuidance(report, item)): string | null {
  const { gap, action, plan, text } = guidance;
  if (!plan && !text?.advice) return null;
  const actionSource = action && ACTION_SOURCE_LABELS[action.source];
  return [
    `岗位：${displayJobTitle(report.jobTitle, report.jobId) || "本报告岗位"}`,
    `岗位要求：${item.requirementTitle}`,
    `材料支持状态：${workspaceStatusLabel(item)}`,
    `当前证据缺口/待核对：${gap || "尚无保存说明，请核对来源。"}`,
    ...(text?.advice ? [`已保存补证建议${actionSource ? `（${actionSource}）` : ""}：${text.advice}`] : []),
    ...(text?.gap ? [`报告补充说明：${text.gap}`] : []),
    ...(plan ? supplementPlanLines(plan) : []),
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

/** A completed upload replaces a version only within the same owned project. */
export function reportReanalysisHref(
  report: Pick<MatchReport, "id" | "jobId" | "materials">,
  uploaded: { kind: "resume" | "project"; versionId: string },
  project?: { versionIds: readonly string[]; sourceVersionId?: string | null },
  requirementId?: string,
): string | null {
  if (!UUID.test(report.jobId) || !UUID.test(uploaded.versionId)) return null;
  const materials = report.materials;
  const reportResume = materials.find(material => material.kind === "resume")?.id;
  const reportProjects = materials.filter(material => material.kind === "project").map(material => material.id);
  let resumeVersionId = reportResume;
  let projectVersionIds = reportProjects;
  if (uploaded.kind === "resume") {
    resumeVersionId = uploaded.versionId;
  } else {
    if (!project?.versionIds.includes(uploaded.versionId)) return null;
    const sameProject = reportProjects.filter(id => project.versionIds.includes(id));
    const replace = sameProject.length === 1 ? sameProject[0] : sameProject.find(id => id === project.sourceVersionId);
    if (sameProject.length && !replace) return null;
    if (!replace && reportProjects.length >= 10) return null;
    projectVersionIds = replace
      ? reportProjects.map(id => id === replace ? uploaded.versionId : id)
      : [...reportProjects, uploaded.versionId];
  }
  if (!resumeVersionId) return null;
  return reportJobHref(report, requirementId, resumeVersionId, projectVersionIds);
}

export function reportJobHref(
  report: Pick<MatchReport, "id" | "jobId" | "materials">,
  requirementId?: string,
  resumeVersionId = report.materials.find(material => material.kind === "resume")?.id,
  projectVersionIds = report.materials.filter(material => material.kind === "project").map(material => material.id),
) {
  const params = new URLSearchParams({ compareTo: report.id });
  if (resumeVersionId) params.set("resumeVersionId", resumeVersionId);
  if (requirementId && UUID.test(requirementId)) params.set("sourceRequirement", requirementId);
  for (const id of projectVersionIds) params.append("projectVersionId", id);
  return `/jobs/${report.jobId}?${params.toString()}`;
}

/** These parameters are navigation hints only; the receiver checks the owned report. */
export function reportUploadHref(reportId: string, requirementId: string, projectVersionId?: string): string {
  return UUID.test(reportId) && UUID.test(requirementId)
    ? `/portfolio?${new URLSearchParams({ sourceReport: reportId, sourceRequirement: requirementId, add:"project", ...(projectVersionId && UUID.test(projectVersionId) ? {sourceProjectVersion:projectVersionId}: {}) })}` : "/portfolio";
}
