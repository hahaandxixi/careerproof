/**
 * Pure display helpers for the analysis-task page.
 *
 * Everything here decides only *how to describe data the API already returned*; no
 * helper invents progress, steps, durations or connection states. Kept free of React so
 * the rules can be tested directly.
 */

export type ConnectionState = "connecting" | "live" | "polling" | "idle";

export interface StepLike {
  name: string;
  eventType: string;
}

/**
 * Only a recorded completion event earns a tick.
 *
 * Production step events, from their generation sites:
 *   `tool.completed`        match_agent.py:41/48/58 (解析简历/扫描项目/可追溯匹配) and
 *                           analysis.py:1175 (every persisted match step, including
 *                           retrieval steps and 模型证据分析)
 *   `task.completed`        match_agent.py:86 (生成结论)
 *   `verification.completed` application_verification.py:746 when successful
 *   `verification.unavailable` same site when not successful — explicitly NOT a completion
 *
 * This predicate is therefore not merely a string trick: each `.completed` name is
 * emitted by a site that has actually reached that stage, and the one `.unavailable`
 * name is emitted when the stage did not finish.
 */
export function isCompletedRecord(eventType: string) {
  return eventType.endsWith(".completed");
}

/**
 * A model step records `tool.completed` even when the model was skipped or degraded, so
 * the tick alone would read as "AI analysis succeeded". This qualifier restores the
 * distinction using only payload fields the model step actually carries.
 */
export function modelStepQualifier(payload: Record<string, unknown> | null | undefined) {
  if (!payload) return null;
  const skipped = payload.skippedReason;
  if (typeof skipped === "string" && skipped.trim()) return "未调用模型";
  if (payload.fallbackUsed === true) return "模型已降级";
  return null;
}

export function completionCount(steps: readonly StepLike[]) {
  return steps.filter((step) => isCompletedRecord(step.eventType)).length;
}

/**
 * Duration in seconds, only when both real timestamps are present and ordered.
 * Returns null instead of guessing, so the page can omit the row entirely.
 */
export function realDurationSeconds(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined,
) {
  if (!startedAt || !completedAt) return null;
  const start = Date.parse(startedAt);
  const end = Date.parse(completedAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return (end - start) / 1000;
}

export function formatSeconds(seconds: number) {
  return `${Math.round(seconds * 10) / 10} 秒`;
}

/**
 * The three processing modes are reported separately and never merged: a degraded
 * model run, an AI-assisted run, and a rules-only run.
 */
export function taskModeLabel(options: { usedAI: boolean; fellBack: boolean; active?: boolean; modelRecorded?: boolean }) {
  if (options.modelRecorded === false) {
    return options.active ? "处理中，外部 AI 调用结果待确认" : "未记录模型处理结果";
  }
  if (options.fellBack) return "模型已降级，本次为规则结果";
  if (options.usedAI) return "AI 解释已参与";
  return "规则模式（未使用外部 AI）";
}

/**
 * Connection wording is derived only from states the component actually observed.
 *
 * `streamSupported === false` means the environment has no EventSource (not a drop).
 * `streamOpened` records whether a stream ever reached `onopen`, so a first-connect or
 * fetch failure is not described as an interruption.
 */
export function connectionLabel(
  state: ConnectionState,
  streamSupported: boolean | null,
  streamOpened = false,
) {
  if (state === "live") return "实时更新中";
  if (state === "polling") {
    if (streamSupported === false) return "当前环境不支持实时推送，已改为定时刷新";
    if (streamOpened) return "实时连接已中断，正在定时刷新";
    return "实时进度暂未建立，正在定时刷新";
  }
  if (state === "connecting") return "正在连接实时进度";
  return "任务已结束，状态不再变化";
}

/** The current-stage line: real step text when present, neutral wording otherwise. */
export function stageText(currentStep: string | null | undefined, active: boolean) {
  const step = currentStep?.trim();
  if (step) return step;
  return active ? "正在准备处理" : "本次任务没有记录当前阶段";
}
