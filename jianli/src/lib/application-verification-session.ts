import type { ApplicationVerificationTask, MatchReport, ReportItem } from "./api/domain";

export interface ApplicationVerificationState {
  task: ApplicationVerificationTask | null;
  loading: boolean;
  error: string;
  notice: string;
}

export const initialApplicationVerificationState: ApplicationVerificationState = {
  task: null, loading: false, error: "", notice: "",
};

// Show safe, actionable categories rather than arbitrary provider error text.
export function verificationFailureMessage(task: ApplicationVerificationTask): string {
  const messages: Record<string, string> = {
    input_budget: "本次输入超过保守预算，已在外发前停止。请缩小授权材料范围后再核对。",
    output_budget: "本次输出额度不足，建议未生成。请核对额度后再操作。",
    daily_budget: "今日 AI 用量已达上限。可继续人工核对原报告，或稍后读取已保存建议。",
    output_truncated: "模型回答被截断，未保存为有效建议。原报告仍可用于人工核验。",
    visible_code_fact_conflict: "模型回答与可见代码事实冲突，已拒绝展示。请核对原报告引用。",
    saved_validation_failed: "已保存的核验建议未通过当前固定报告校验，已隐藏。请核对原报告；重新生成需要再次确认模型外发范围。",
    authorization_revoked: "投递授权已变化，请刷新授权投递重新核对。",
    snapshot_changed: "岗位或投递快照已变化，请刷新授权投递重新核对。",
    provider_timeout: "模型服务响应超时；没有自动重试。可继续人工核对原报告。",
    workflow_timeout: "生成任务超时；没有自动重试。可继续人工核对原报告。",
    provider_network: "模型服务连接失败；没有自动重试。可继续人工核对原报告。",
  };
  const kind = task.failureKind || "";
  return Object.hasOwn(messages, kind) ? messages[kind] : "本次 AI 核验建议未生成或未通过校验；没有自动重试。请继续核对原报告。";
}

interface Dependencies {
  latest(signal: AbortSignal): Promise<ApplicationVerificationTask | null>;
  create(signal: AbortSignal): Promise<ApplicationVerificationTask>;
  read(taskId: string, signal: AbortSignal): Promise<ApplicationVerificationTask | null>;
  errorMessage(error: unknown): string;
  unavailable(error: unknown): boolean;
  onUnavailable(): void;
  accepts(task: ApplicationVerificationTask): boolean;
}

// Only frozen report requirements and their own citation whitelist may be shown.
export function applicationVerificationSources(item: ReportItem) {
  return item.evidenceList?.length ? item.evidenceList : item.evidence ? [item.evidence] : [];
}

export function verificationMatchesReport(task: ApplicationVerificationTask, report: MatchReport): boolean {
  if (!task.analysis) return true;
  const seen = new Set<string>();
  return task.analysis.items.length === report.items.length && task.analysis.items.every(item => {
    const requirement = report.items.find(value => value.requirementId === item.requirementId);
    if (!requirement || seen.has(item.requirementId)) return false;
    seen.add(item.requirementId);
    const allowed = new Set(applicationVerificationSources(requirement).map(evidence => evidence.citationId).filter(Boolean));
    return item.citationIds.every(id => allowed.has(id));
  });
}

// Cancelling local reads never cancels a server task or silently generates a new
// task. Reopening the authorized application reads its saved result again.
export function createApplicationVerificationSession(
  api: Dependencies,
  publish: (state: ApplicationVerificationState) => void,
  options: { pollMs?: number; maxPolls?: number } = {},
) {
  const pollMs = options.pollMs ?? 1500;
  const maxPolls = options.maxPolls ?? 60;
  let active = false;
  let generation = 0;
  let polls = 0;
  let state = initialApplicationVerificationState;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;
  const current = (ticket: number) => active && generation === ticket;
  const set = (next: ApplicationVerificationState) => { state = next; publish(next); };
  function cancel() {
    ++generation;
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    controller?.abort();
    controller = undefined;
  }

  function accept(task: ApplicationVerificationTask | null, ticket: number) {
    if (!current(ticket)) return;
    if (task && !api.accepts(task)) {
      set({ ...initialApplicationVerificationState, error: "无法核对建议对应的固定报告要求或引用。请刷新授权投递后重试。" });
      return;
    }
    const waiting = task?.status === "pending" || task?.status === "running";
    const failed = task?.status === "failed" || task?.status === "cancelled";
    set({ task, loading: !!waiting, error: failed ? verificationFailureMessage(task) : "", notice: "" });
    if (waiting && task) {
      if (polls >= maxPolls) {
        set({ ...state, loading: false, notice: "任务仍在处理中，已停止自动查询。稍后点击“读取已保存建议”核对结果；读取不会新增模型调用。" });
        return;
      }
      timer = setTimeout(() => { timer = undefined; ++polls; void read(() => api.read(task.taskId, controller!.signal), ticket); }, pollMs);
    }
  }

  async function read(operation: () => Promise<ApplicationVerificationTask | null>, ticket: number) {
    try {
      const task = await operation();
      if (current(ticket)) accept(task, ticket);
    } catch (error) {
      if (!current(ticket)) return;
      if (api.unavailable(error)) {
        set({ ...initialApplicationVerificationState, error: "该投递的 AI 建议已不可访问，已清除建议。请刷新授权投递重新核对。" });
        api.onUnavailable();
      } else {
        // A read failure stops polling and removes previously displayed AI text.
        set({ ...initialApplicationVerificationState, error: `${api.errorMessage(error)} 原报告仍可用于人工核验；可稍后读取已保存建议。` });
      }
    }
  }

  function run(operation: (signal: AbortSignal) => Promise<ApplicationVerificationTask | null>) {
    if (!active || state.loading) return Promise.resolve();
    cancel();
    const ticket = generation;
    polls = 0;
    controller = new AbortController();
    set({ ...initialApplicationVerificationState, loading: true });
    return read(() => operation(controller!.signal), ticket);
  }

  return {
    activate() { active = true; state = initialApplicationVerificationState; },
    load() { return run(api.latest); },
    generate(consented: boolean) {
      if (!active || state.loading || !consented) return Promise.resolve();
      return run(api.create);
    },
    clear() { cancel(); active = false; set({ ...initialApplicationVerificationState }); },
    dispose() { cancel(); active = false; },
  };
}
