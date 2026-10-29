"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage, type AnalysisTask } from "@/lib/api/client";
import { taskUsedExternalAI } from "@/lib/analysis-status";
import {
  completionCount,
  connectionLabel,
  formatSeconds,
  isCompletedRecord,
  modelStepQualifier,
  realDurationSeconds,
  stageText,
  taskModeLabel,
  type ConnectionState,
} from "@/lib/process-trace";
import { ErrorNotice } from "./AccessGate";
import MaterialContentNotice from "./MaterialContentNotice";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const MODEL_STEPS = ["模型证据分析", "千问证据分析"];
const LABELS: Record<string, string> = { pending: "等待处理", running: "正在分析", completed: "处理完成", failed: "处理失败", cancelled: "已取消" };
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
  // null until the first client effect: avoids claiming either capability during SSR.
  const [streamSupported, setStreamSupported] = useState<boolean | null>(null);
  // True once a stream actually reached onopen, so a first-connect failure is not
  // reported as an interrupted connection.
  const [streamOpened, setStreamOpened] = useState(false);

  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let source: EventSource | undefined;
    setError("");
    setConnection("connecting");
    setStreamSupported(typeof EventSource !== "undefined");
    setStreamOpened(false);

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
      source.onopen = () => { if (current) { setConnection("live"); setStreamOpened(true); } };
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
  const aiStep = task?.steps.find(step => MODEL_STEPS.includes(step.name));
  const usedAI = taskUsedExternalAI(aiStep?.payload.provider, aiStep?.payload.fallbackUsed);
  const fellBack = aiStep?.payload.fallbackUsed === true;
  const active = task ? !TERMINAL.has(task.status) : false;
  // A missing model record during retrieval is not evidence of a rules-only run.
  const modeLabel = taskModeLabel({ usedAI, fellBack, active, modelRecorded: !!aiStep });
  const duration = task ? realDurationSeconds(task.startedAt, task.completedAt) : null;
  const completionRecords = task ? completionCount(task.steps) : 0;
  const connectionText = connectionLabel(connection, streamSupported, streamOpened);
  return <div className="mx-auto max-w-3xl space-y-6">
    <div className="flex gap-4 text-sm text-indigo-600"><Link href="/portfolio">我的材料</Link><Link href="/reports">匹配报告</Link></div>
    <h1 className="text-3xl font-bold">分析任务</h1>
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {!task && !error && <p className="text-sm text-slate-500">正在加载任务…</p>}
    {task && <>
      <section className="panel">
        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{LABELS[task.status] ?? task.status}</h2><span className="text-sm text-slate-500">{Math.round(task.progress)}%</span></div>
        <progress className="task-progress mt-4 h-3 w-full accent-indigo-600" max={100} value={task.progress} aria-label="分析进度" />
        {/* aria-live stays on this short line only; the history below is not re-announced. */}
        <p role="status" className="task-stage mt-3 text-sm text-slate-700">
          {active && <span className="task-stage-dot" aria-hidden="true" />}
          <span>{stageText(task.currentStep, active)}</span>
        </p>
        {task.errorMessage && <p className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{task.errorMessage}</p>}
        <dl className="mt-4 grid gap-x-6 gap-y-1 text-xs text-slate-500 sm:grid-cols-2">
          <div><dt className="inline">创建时间：</dt><dd className="inline">{new Date(task.createdAt).toLocaleString("zh-CN")}</dd></div>
          <div><dt className="inline">处理方式：</dt><dd className="inline">{modeLabel}</dd></div>
          {/* Only real start/end timestamps produce a duration. */}
          {duration !== null && <div><dt className="inline">实际处理时长：</dt><dd className="inline">{formatSeconds(duration)}</dd></div>}
          <div><dt className="inline">进度连接：</dt><dd className="inline">{connectionText}</dd></div>
        </dl>
        <div className="mt-5 flex flex-wrap gap-3">{task.reportId && <Link className="btn" href={`/reports/${task.reportId}`}>查看匹配报告</Link>}{task.status === "failed" && <button className="btn-secondary" disabled={busy} onClick={() => void retry()}>{busy ? "提交重试…" : "重试此任务"}</button>}{task.status === "completed" && !task.reportId && <Link className="btn" href="/portfolio">返回材料，查看解析结果</Link>}</div>
        {task.status === "failed" && <p className="mt-3 text-xs text-slate-500">重试会复用原材料版本。如果文件本身不受支持，请上传修正后的新版本。</p>}
      </section>
      {task.steps.filter(step => step.eventType === "material.content_warning").map(step =>
        <MaterialContentNotice key={step.step} report={step.payload} />)}
      <details className="panel">
        <summary className="cursor-pointer font-semibold">实际处理记录{completionRecords > 0 && <span className="ml-2 text-xs font-normal text-slate-500">已有 {completionRecords} 条完成记录</span>}</summary>
        {!task.steps.length
          ? <p className="mt-3 text-sm text-slate-500">{active ? "任务仍在执行，当前阶段会在上方实时更新。" : "该材料处理任务未记录细分步骤。"}</p>
          : <ol className="mt-4 space-y-4">{task.steps.map((step, index) => <li key={`${step.step}-${index}`} className="border-l-2 border-indigo-200 pl-4">
              <p className="text-sm font-medium">
                {isCompletedRecord(step.eventType) && !(MODEL_STEPS.includes(step.name) && modelStepQualifier(step.payload))
                  ? <span className="mr-1 text-indigo-700" aria-hidden="true">✓</span>
                  : null}
                <span>{step.name}</span>
                {/* A model step records tool.completed even when the model was skipped
                    or degraded; name that state so the tick is not read as AI success. */}
                {MODEL_STEPS.includes(step.name) && (() => {
                  const qualifier = modelStepQualifier(step.payload);
                  return qualifier ? <span className="ml-2 text-xs font-normal text-slate-700">{qualifier}</span> : null;
                })()}
                {isCompletedRecord(step.eventType) && <span className="sr-only">（已完成记录）</span>}
              </p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-500">{step.detail}</p>
              {MODEL_STEPS.includes(step.name) && typeof step.payload.latencyMs === "number" && step.payload.latencyMs > 0 && <p className="mt-1 text-xs text-slate-400">耗时 {Math.round((step.payload.latencyMs as number) / 100) / 10} 秒 · 输入 {String(step.payload.inputTokens ?? 0)} tokens · 输出 {String(step.payload.outputTokens ?? 0)} tokens</p>}
            </li>)}</ol>}
      </details>
    </>}
  </div>;
}
