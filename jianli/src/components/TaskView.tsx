"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage, type AnalysisTask } from "@/lib/api/client";
import { taskUsedExternalAI } from "@/lib/analysis-status";
import { ErrorNotice } from "./AccessGate";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const LABELS: Record<string, string> = { pending: "等待处理", running: "正在分析", completed: "处理完成", failed: "处理失败", cancelled: "已取消" };
type ConnectionState = "connecting" | "live" | "polling" | "idle";
interface TaskProgressEvent {
  taskId: string;
  status: AnalysisTask["status"];
  progress: number;
  currentStep: string | null;
  errorMessage: string | null;
}

export default function TaskView({ id }: { id: string }) {
  const router = useRouter();
  const [task, setTask] = useState<AnalysisTask | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [connection, setConnection] = useState<ConnectionState>("connecting");

  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let source: EventSource | undefined;
    setError("");
    setConnection("connecting");

    function stopStream() {
      source?.close();
      source = undefined;
    }

    function schedulePoll() {
      if (!current || timer) return;
      setConnection("polling");
      timer = setTimeout(() => {
        timer = undefined;
        void loadTask(true);
      }, 1800);
    }

    function applyEvent(event: MessageEvent<string>) {
      let update: TaskProgressEvent;
      try {
        update = JSON.parse(event.data) as TaskProgressEvent;
      } catch {
        stopStream();
        schedulePoll();
        return;
      }
      if (!current || update.taskId !== id) return;
      setTask((previous) => previous ? {
        ...previous,
        status: update.status,
        progress: update.progress,
        currentStep: update.currentStep,
        errorMessage: update.errorMessage,
      } : previous);
      setError("");
      if (TERMINAL.has(update.status)) {
        stopStream();
        setConnection("idle");
        void loadTask(false);
      }
    }

    function openStream() {
      if (!current || source || typeof EventSource === "undefined") {
        if (typeof EventSource === "undefined") schedulePoll();
        return;
      }
      source = new EventSource(api.analysisTaskEventsUrl(id), { withCredentials: true });
      source.onopen = () => { if (current) setConnection("live"); };
      source.addEventListener("task.progress", applyEvent as EventListener);
      source.addEventListener("task.completed", applyEvent as EventListener);
      source.addEventListener("task.failed", applyEvent as EventListener);
      source.onerror = () => {
        stopStream();
        schedulePoll();
      };
    }

    async function loadTask(continueUpdates: boolean) {
      try {
        const value = await api.getAnalysisTask(id);
        if (!current) return;
        setTask(value);
        setError("");
        if (TERMINAL.has(value.status)) {
          stopStream();
          setConnection("idle");
        } else if (continueUpdates) {
          if (connection === "polling") schedulePoll();
          else openStream();
        }
      } catch (reason) {
        if (!current) return;
        setError(errorMessage(reason));
        if (continueUpdates) schedulePoll();
      }
    }

    void loadTask(true);
    return () => {
      current = false;
      stopStream();
      if (timer) clearTimeout(timer);
    };
  // A revision intentionally restarts both the initial read and the event stream.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, revision]);

  async function retry() {
    setBusy(true); setError("");
    try {
      const accepted = await api.retryTask(id);
      if (accepted.taskId !== id) router.push(`/tasks/${accepted.taskId}`);
      else setRevision(value => value + 1);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  const aiStep = task?.steps.find(step => ["模型证据分析", "千问证据分析"].includes(step.name));
  const usedAI = taskUsedExternalAI(aiStep?.payload.provider, aiStep?.payload.fallbackUsed);
  const fellBack = aiStep?.payload.fallbackUsed === true;
  return <div className="mx-auto max-w-3xl space-y-6">
    <div className="flex gap-4 text-sm text-indigo-600"><Link href="/portfolio">我的材料</Link><Link href="/reports">匹配报告</Link></div>
    <h1 className="text-3xl font-bold">分析任务</h1>
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {!task && !error && <p className="text-sm text-slate-500">正在加载任务…</p>}
    {task && <>
      <section className="panel"><div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{LABELS[task.status] ?? task.status}</h2><span className="text-sm text-slate-500">{Math.round(task.progress)}%</span></div>
        <progress className="mt-4 h-3 w-full accent-indigo-600" max={100} value={task.progress} aria-label="分析进度" />
        <p role="status" className="mt-3 text-sm text-slate-600">{task.currentStep || "正在准备处理"}</p>
        {task.errorMessage && <p className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{task.errorMessage}</p>}
        <p className="mt-4 text-xs text-slate-500">创建于 {new Date(task.createdAt).toLocaleString("zh-CN")} · {usedAI ? "规则证据 + AI 解释" : fellBack ? "模型已降级，使用规则报告" : "证据约束分析"} · {connection === "live" ? "实时更新" : connection === "polling" ? "连接中断，自动轮询" : connection === "connecting" ? "正在连接实时进度" : "任务状态已固定"}</p>
        <div className="mt-5 flex flex-wrap gap-3">{task.reportId && <Link className="btn" href={`/reports/${task.reportId}`}>查看匹配报告</Link>}{task.status === "failed" && <button className="btn-secondary" disabled={busy} onClick={() => void retry()}>{busy ? "提交重试…" : "重试此任务"}</button>}{task.status === "completed" && !task.reportId && <Link className="btn" href="/portfolio">返回材料，查看解析结果</Link>}</div>
        {task.status === "failed" && <p className="mt-3 text-xs text-slate-500">重试会复用原材料版本。如果文件本身不受支持，请上传修正后的新版本。</p>}
      </section>
      <section className="panel"><h2 className="font-semibold">实际处理记录</h2>{!task.steps.length ? <p className="mt-3 text-sm text-slate-500">{task.status === "pending" || task.status === "running" ? "任务执行中，当前阶段会在上方实时更新。" : "该材料处理任务未记录细分步骤。"}</p> : <ol className="mt-4 space-y-4">{task.steps.map((step, index) => <li key={`${step.step}-${index}`} className="border-l-2 border-indigo-200 pl-4"><p className="text-sm font-medium">{step.name}</p><p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-500">{step.detail}</p>{["模型证据分析", "千问证据分析"].includes(step.name) && typeof step.payload.latencyMs === "number" && step.payload.latencyMs > 0 && <p className="mt-1 text-xs text-slate-400">耗时 {Math.round(step.payload.latencyMs / 100) / 10} 秒 · 输入 {String(step.payload.inputTokens ?? 0)} tokens · 输出 {String(step.payload.outputTokens ?? 0)} tokens</p>}</li>)}</ol>}</section>
    </>}
  </div>;
}
