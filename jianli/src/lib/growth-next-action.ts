import type { GrowthTask } from "./api/domain";
/** Navigation only: saving/analyzing still requires the existing explicit form actions. */
export function growthNextAction(task: GrowthTask, unsaved: boolean) {
  if (task.targetReportId) return { label: "查看本次变化", target: task.comparison ? `growth-requirement-${task.requirementId}` : "growth-processing" };
  if (task.analysisTaskId) return { label: task.status === "analysis_failed" ? "核对失败原因与恢复入口" : "查看处理进度", target: "growth-processing" };
  if (unsaved) return { label: "核对并保存本次材料选择", target: "growth-save" };
  if (task.materials.length) return { label: "前往生成新报告", target: "growth-analysis" };
  return { label: "准备本轮材料", target: "growth-materials" };
}
