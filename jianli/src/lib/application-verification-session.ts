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
    budget_cutover_not_enabled: "AI 核验暂未开放，未发送材料。可继续核对固定报告。",
    budget_cutover_evidence_missing: "AI 核验暂不可用，未发送材料。请联系管理员。",
    input_budget: "本次材料超出可发送范围，未发送。请人工核对固定报告。",
    output_budget: "本次生成额度不足，请稍后再试。",
    daily_budget: "今日 AI 用量已达上限。可继续核对固定报告。",
    daily_input_token_limit: "今日 AI 用量已达上限。可继续核对固定报告。",
    daily_output_token_limit: "今日 AI 用量已达上限。可继续核对固定报告。",
    output_truncated: "模型回答不完整，未保存建议。可继续核对固定报告。",
    visible_code_fact_conflict: "模型回答与授权代码冲突，未保存建议。请核对原报告引用。",
    saved_validation_failed: "已保存建议未通过固定报告校验。请核对原报告。",
    authorization_revoked: "投递授权已变化，请刷新授权投递。",
    snapshot_changed: "岗位或投递快照已变化，请刷新授权投递。",
    provider_timeout: "模型响应超时。可刷新结果或继续核对固定报告。",
    workflow_timeout: "生成超时。可刷新结果或继续核对固定报告。",
    provider_network: "模型服务连接失败。可稍后重试。",
    provider_http_401: "模型服务鉴权失败，请联系管理员。",
    provider_http_403: "模型服务拒绝访问，请联系管理员。",
    provider_http_402: "模型服务额度不足，请联系管理员。",
    provider_http_429: "模型服务请求受限，请稍后再试。",
    provider_configuration: "模型服务未配置完成，请联系管理员。",
    invalid_model_output: "模型回答未通过校验。请核对固定报告。",
    receipt_persistence_failed: "本次模型结果未能确认，请刷新结果。",
  };
  const kind = task.failureKind || "";
  return Object.hasOwn(messages, kind) ? messages[kind] : "本次没有有效的核验建议。可继续核对固定报告。";
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
        set({ ...state, loading: false, notice: "任务仍在处理中，请稍后刷新结果。" });
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
        set({ ...initialApplicationVerificationState, error: "该投递的核验建议已不可访问，请刷新授权投递。" });
        api.onUnavailable();
      } else {
        // A read failure stops polling and removes previously displayed AI text.
        set({ ...initialApplicationVerificationState, error: `${api.errorMessage(error)} 可刷新结果。` });
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
