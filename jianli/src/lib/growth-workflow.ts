import type { GrowthTask } from "./api/domain";

export function growthCanSelect(task: GrowthTask) {
  return !task.analysisTaskId || task.status === "analysis_failed";
}

const JOB_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface GrowthTargetJobState {
  originalJobId: string;
  originalJobTitle: string;
  /** 服务器已保存的有效目标；旧任务或未升级后端 = 原岗位。 */
  savedTargetJobId: string;
  savedTargetJobTitle: string;
  /** 当前草稿将保存/使用的目标；空或非 UUID 草稿回落到已保存目标。 */
  effectiveTargetJobId: string;
  /** 草稿与已保存目标不一致：未保存，不得展示为已保存，生成不使用它。 */
  selectionChanged: boolean;
  /** 已保存目标 != 原岗位（跨岗位补证）。 */
  crossJob: boolean;
  /** 非失败分析进行中：岗位与材料选择同时锁定。 */
  locked: boolean;
}

export function growthTargetJobState(task: GrowthTask, selectedTargetJobId: string): GrowthTargetJobState {
  const savedTargetJobId = task.targetJobId || task.jobId;
  const draft = selectedTargetJobId.trim();
  const effectiveTargetJobId = draft && JOB_ID_PATTERN.test(draft) ? draft : savedTargetJobId;
  return {
    originalJobId: task.jobId,
    originalJobTitle: task.jobTitle,
    savedTargetJobId,
    savedTargetJobTitle: task.targetJobTitle || task.jobTitle,
    effectiveTargetJobId,
    selectionChanged: effectiveTargetJobId !== savedTargetJobId,
    crossJob: savedTargetJobId !== task.jobId,
    locked: !growthCanSelect(task),
  };
}

/** 公开岗位列表请求参数；q 可省略，page 从 1 起，避免只读前 100 条。 */
export function growthJobListQuery(query: string, page: number): Record<string, string | number> {
  const trimmed = query.trim();
  return { page: Math.max(1, Math.floor(page)), pageSize: 10, ...(trimmed ? { q: trimmed } : {}) };
}

export function growthJobPageBounds(total: number, page: number, pageSize: number) {
  const current = Math.max(1, Math.floor(page));
  return { hasPrevious: current > 1, hasNext: current * pageSize < total, page: current };
}

/**
 * 保存材料请求的最终载荷。targetJobId 恒为有效 UUID：
 * 清除未保存改选（空草稿）= 明确保持已保存目标（旧任务为原岗位），
 * 明确改选 = 使用改选；不允许省略字段造成“界面说恢复已保存、请求却回到原岗位”。
 */
export function growthSaveMaterialsPayload(
  task: GrowthTask,
  selectedTargetJobId: string,
  materials: { resumeVersionId: string; projectVersionIds: string[] },
): { resumeVersionId: string; projectVersionIds: string[]; targetJobId: string } {
  return { ...materials, targetJobId: growthTargetJobState(task, selectedTargetJobId).effectiveTargetJobId };
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
  job: "目标岗位变化",
  retrieval_version: "检索版本变化", rule_version: "规则版本变化",
  model_or_mode: "模型或分析模式变化", review: "复核状态变化", ai_status: "AI 状态变化",
  level: "等级变化", evidence: "展示证据变化", item_added: "新增要求", item_removed: "移除要求",
  interpretation: "解释或缺口变化",
  advice: "补证建议或执行草稿变化",
};

export const GROWTH_POLL_LIMIT = 60;
export const GROWTH_AUTO_QUERY_STOPPED = "已停止自动查询。任务继续在服务器处理，可点击“刷新任务状态”；不会新增模型调用。";

export interface GrowthAutoQueryInput {
  polls: number;
  analyzing: boolean;
  busy?: boolean;
  error?: string;
}

// One step of the analyzing auto-query effect. A null notice leaves the
// current notice untouched; a string replaces it. Leaving the analyzing
// state clears a stale stop notice, and a fresh poll budget queries normally.
export function growthAutoQueryStep(input: GrowthAutoQueryInput): { poll: boolean; notice: string | null } {
  if (input.busy || input.error) return { poll: false, notice: null };
  if (!input.analyzing) return { poll: false, notice: "" };
  if (input.polls >= GROWTH_POLL_LIMIT) return { poll: false, notice: GROWTH_AUTO_QUERY_STOPPED };
  return { poll: true, notice: "" };
}
