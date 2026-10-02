import type { GrowthTask } from "./api/domain";

export function growthCanSelect(task: GrowthTask) {
  return !task.analysisTaskId || task.status === "analysis_failed";
}

// Local state may be cleared while a server-side operation finishes. It must
// never restore a hidden page or a different account's data.
export function createGrowthRequestGuard() {
  let generation = 0;
  return {
    start: () => ++generation,
    clear: () => { ++generation; },
    accepts: (ticket: number) => ticket === generation,
  };
}

export const GROWTH_STATUS: Record<GrowthTask["status"], string> = {
  planned: "待补充材料", materials_selected: "已选择材料 · 待分析",
  analyzing: "正在分析", analysis_failed: "分析失败 · 记录保留", compared: "新报告已对比 · 待人工核验",
};
export const GROWTH_CHANGES: Record<string, string> = {
  materials: "材料版本变化", requirements: "岗位要求变化", requirement: "该要求变化",
  retrieval_version: "检索版本变化", rule_version: "规则版本变化",
  model_or_mode: "模型或分析模式变化", review: "复核状态变化", ai_status: "AI 状态变化",
  level: "等级变化", evidence: "展示证据变化", item_added: "新增要求", item_removed: "移除要求",
  interpretation: "解释或缺口变化",
  advice: "补证建议或执行草稿变化",
};
