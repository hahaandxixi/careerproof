// 传智杯56：岗位页投递感知。学生匹配表单独立读取 myApplications（只读 GET），
// 与材料加载解耦；只有返回记录能证明具体状态——缺失/残缺/失败一律不做“未投递”结论。
// 撤回史不是进行中的投递；过期/岗位切换/卸载后到达的响应按会话代次丢弃。

import { createRefreshGate } from "./refresh-gate";

export interface JobApplicationRef {
  id: string;
  status: string;
  createdAt: string;
}

export type JobApplicationStatusState =
  // 读取中：不给任何结论。
  | { kind: "loading" }
  // 读取失败：显式报错并允许只读重试；不影响生成报告。
  | { kind: "error"; message: string }
  // 成功返回但没有可判定的本岗位记录：不渲染任何状态（绝不显示“未投递”）。
  | { kind: "unknown" }
  // 本岗位存在未撤回投递：服务端会拒绝替换的那条，取最新。
  | { kind: "active"; application: JobApplicationRef }
  // 本岗位只有已撤回记录：如实呈现为撤回史，不当成进行中、不恢复授权。
  | { kind: "withdrawn"; application: JobApplicationRef };

function validApplicationRef(record: unknown, jobId: string): JobApplicationRef | null {
  if (!record || typeof record !== "object") return null;
  const { id, status, createdAt } = record as { id?: unknown; status?: unknown; createdAt?: unknown };
  if (typeof id !== "string" || !id) return null;
  if (typeof status !== "string" || !status) return null;
  if ((record as { jobId?: unknown }).jobId !== jobId) return null;
  return { id, status, createdAt: typeof createdAt === "string" ? createdAt : "" };
}

// 纯解析：同一岗位的记录里，任何未撤回状态都构成“进行中”（含服务端未来的新状态字面量）；
// 有进行中的就不看撤回史；同组内取 createdAt 最新，时间相同取数组靠后的（跟随服务端顺序）。
export function resolveJobApplicationStatus(records: readonly unknown[], jobId: string): JobApplicationStatusState {
  let active: JobApplicationRef | null = null;
  let withdrawn: JobApplicationRef | null = null;
  records.forEach(record => {
    const ref = validApplicationRef(record, jobId);
    if (!ref) return;
    const pick = (current: JobApplicationRef | null): JobApplicationRef =>
      !current || ref.createdAt >= current.createdAt ? ref : current;
    if (ref.status !== "withdrawn") active = pick(active);
    else withdrawn = pick(withdrawn);
  });
  if (active) return { kind: "active", application: active };
  if (withdrawn) return { kind: "withdrawn", application: withdrawn };
  return { kind: "unknown" };
}

export interface JobApplicationStatusSession {
  activate(): void;
  dispose(): void;
  clear(): void;
  refresh(jobId: string): Promise<void>;
}

// 会话控制器：代次票据保证只有最后一次 refresh 的响应能发布；
// dispose 后到达的响应被丢弃（response-after-unmount）。refresh 先同步发布 loading，
// 岗位/身份切换时上一岗位的数据立即被清空（身份切换另由组件层 key 重挂载兜底）。
export function createJobApplicationStatusSession(deps: {
  api: { myApplications(): Promise<unknown[]>; errorMessage(error: unknown): string };
  publish(value: JobApplicationStatusState): void;
}): JobApplicationStatusSession {
  let active = false;
  let generation = 0;
  const current = (ticket: number) => active && ticket === generation;
  return {
    activate() { active = true; },
    dispose() { active = false; ++generation; },
    clear() { ++generation; deps.publish({ kind: "loading" }); },
    async refresh(jobId: string) {
      if (!active) return;
      const ticket = ++generation;
      deps.publish({ kind: "loading" });
      try {
        const records = await deps.api.myApplications();
        if (!current(ticket)) return;
        deps.publish(resolveJobApplicationStatus(records, jobId));
      } catch (error) {
        if (current(ticket)) deps.publish({ kind: "error", message: deps.api.errorMessage(error) });
      }
    },
  };
}

// Returning to the page rechecks the saved status; clearing invalidates in-flight
// reads without touching material choices or consent owned by the matching form.
export function bindJobApplicationStatusLifecycle(session: JobApplicationStatusSession, jobId: string, events: {
  page: EventTarget; document: EventTarget & { visibilityState: string };
}) {
  session.activate();
  const gate = createRefreshGate(() => { void session.refresh(jobId); });
  const clear = () => { session.clear(); gate.reset(); };
  const refreshVisible = () => { if (events.document.visibilityState === "visible") gate.trigger(); };
  const visibility = () => events.document.visibilityState === "hidden" ? clear() : refreshVisible();
  events.document.addEventListener("visibilitychange", visibility);
  events.page.addEventListener("focus", refreshVisible);
  events.page.addEventListener("pageshow", refreshVisible);
  events.page.addEventListener("blur", clear);
  refreshVisible();
  return () => {
    events.document.removeEventListener("visibilitychange", visibility);
    events.page.removeEventListener("focus", refreshVisible);
    events.page.removeEventListener("pageshow", refreshVisible);
    events.page.removeEventListener("blur", clear);
    session.dispose();
  };
}
