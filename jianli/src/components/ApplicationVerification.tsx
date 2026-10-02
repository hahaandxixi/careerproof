"use client";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import type { VerificationReplyQuestion } from "@/lib/verification-reply-draft";
import {
  applicationVerificationSources, createApplicationVerificationSession, initialApplicationVerificationState, verificationMatchesReport,
} from "@/lib/application-verification-session";

const NEXT_STEP = {
  review_materials: "继续核对已授权材料",
  request_evidence: "向学生提出补证请求",
  discuss_implementation: "人工沟通具体实现",
};

export default function ApplicationVerification({ applicationId, report, onUnavailable, onUseQuestion }: {
  applicationId: string; report: MatchReport; onUnavailable(): void;
  onUseQuestion?: (question: VerificationReplyQuestion) => void;
}) {
  const [state, setState] = useState(initialApplicationVerificationState);
  const [consent, setConsent] = useState(false);
  const session = useMemo(() => createApplicationVerificationSession({
    latest: signal => api.applicationVerification(applicationId, undefined, signal),
    create: signal => api.createApplicationVerification(applicationId, signal),
    read: (taskId, signal) => api.applicationVerification(applicationId, taskId, signal),
    errorMessage,
    unavailable: error => error instanceof ApiError && (error.status === 403 || error.status === 404),
    onUnavailable,
    accepts: task => verificationMatchesReport(task, report),
  }, setState), [applicationId, report, onUnavailable]);

  useEffect(() => {
    session.activate();
    void session.load();
    const visibility = () => {
      if (document.visibilityState === "hidden") { setConsent(false); session.clear(); }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => { session.dispose(); document.removeEventListener("visibilitychange", visibility); };
  }, [session]);

  const { task, loading, error, notice } = state;
  const analysis = task?.status === "completed" && task.aiStatus === "validated" ? task.analysis : null;
  return <section className="space-y-4 rounded-xl border border-indigo-200 bg-indigo-50/30 p-4 sm:p-5" aria-labelledby="verification-title">
    <h3 id="verification-title" className="text-lg font-semibold">企业 AI 核验建议</h3>
    <p className="text-sm leading-6 text-slate-600">依据该岗位当前要求、本次投递固定报告中的要求和已授权引用片段，整理可见支持、材料缺口和核验问题。建议供企业人工确认，不改变报告分数或实践等级，不自动发送回复或作招聘决定。</p>
    <label className="flex items-start gap-2 text-sm leading-6">
      <input type="checkbox" className="mt-1.5 shrink-0" checked={consent} disabled={loading} onChange={event => setConsent(event.target.checked)} />
      <span>我同意将该岗位当前要求、本次投递固定报告中的要求和已授权引用片段发送给 DeepSeek 官方 API，用于生成核验建议。</span>
    </label>
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" className="btn" disabled={loading || !consent} onClick={() => void session.generate(consent)}>生成或复用核验建议</button>
      <button type="button" className="text-sm text-indigo-700 underline disabled:text-slate-400" disabled={loading} onClick={() => void session.load()}>读取已保存建议</button>
    </div>
    <p className="text-xs leading-5 text-slate-500">读取已有结果不新增模型调用；同一投递快照优先复用已保存建议。授权变化时停止展示，刷新投递或离开窗口会收起建议。</p>
    <p className="text-xs leading-5 text-amber-800">岗位当前要求可能与投递时要求不同，请核对各项对应关系和变化；固定报告保留投递时依据。</p>
    {loading && <p role="status" className="text-sm text-indigo-800">{task ? "正在生成核验建议，已授权范围会再次核对…" : "正在核对已保存的核验建议…"}</p>}
    {notice && <p role="status" className="text-sm leading-6 text-amber-800">{notice}</p>}
    {error && <p role="alert" className="text-sm leading-6 text-rose-700">{error}</p>}
    {!loading && !task && !error && <p className="text-sm text-slate-500">尚无已保存的核验建议，可确认外发范围后生成。</p>}
    {task && !loading && task.status === "completed" && !analysis && <p role="status" className="text-sm text-amber-800">{task.failureKind === "saved_validation_failed" ? "已保存建议未通过当前固定报告校验，已隐藏。请核对原报告；如需重新生成，请重新确认外发范围。" : "本次没有可展示的有效 AI 建议，请继续核对原报告。"}</p>}
    {analysis && <div className="space-y-4">
      <p className="break-all text-xs leading-5 text-slate-500">{task?.aiModel || "DeepSeek"} · {task?.promptVersion} · 生成于 {task?.createdAt ? new Date(task.createdAt).toLocaleString("zh-CN") : "—"}{task?.reused ? " · 已复用" : ""}</p>
      {analysis.items.map(item => {
        const requirement = report.items.find(value => value.requirementId === item.requirementId)!;
        const evidence = applicationVerificationSources(requirement).filter(value => value.citationId && item.citationIds.includes(value.citationId));
        return <article key={item.requirementId} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm leading-6">
          <h4 className="font-semibold">{requirement.requirementTitle || requirement.skill}</h4>
          <div><p className="font-medium text-slate-800">可见支持</p><p className="whitespace-pre-wrap break-words">{item.visibleSupport || "本次授权片段未展示足够支持，需人工核验。"}</p></div>
          <div><p className="font-medium text-amber-800">材料缺口与边界</p><p className="whitespace-pre-wrap break-words">{item.informationGap}</p></div>
          <div><p className="font-medium text-slate-800">建议人工核验的问题</p><ol className="list-decimal space-y-2 pl-5">{item.verificationQuestions.map((question, index) => <li key={index} className="whitespace-pre-wrap break-words">{question}{onUseQuestion && <button type="button" className="ml-2 text-indigo-700 underline" onClick={() => onUseQuestion({ requirementId: item.requirementId, requirementIndex: report.items.indexOf(requirement), requirementTitle: requirement.requirementTitle || requirement.skill, question, citationIds: item.citationIds })}>加入回复草稿</button>}</li>)}</ol></div>
          {item.nextStep && <div className="rounded-lg bg-slate-50 p-3"><p className="font-medium">可选下一步：{NEXT_STEP[item.nextStep]}</p><p className="whitespace-pre-wrap break-words">{item.nextStepReason}</p><p className="mt-1 text-xs text-slate-500">由企业自行确认和执行，此建议不会自动发给学生。</p></div>}
          {evidence.length ? <details><summary className="cursor-pointer text-indigo-700">查看建议引用的授权片段（{evidence.length}）</summary><div className="space-y-3 pt-2">{evidence.map((source, index) => <div key={`${source.citationId}:${index}`} className="text-xs leading-5"><p className="break-all">{source.citationId} · {source.filePath} · 第{source.lineStart}—{source.lineEnd}行</p>{source.provenance === "reference" && <p className="text-amber-800">参考材料，不构成学生本人实践证明。</p>}<pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2">{source.snippet}</pre><p className="mt-1 text-slate-500">{source.contextNote}</p></div>)}</div></details> : <p className="text-xs text-slate-500">本项没有支持引用；问题和补证建议不构成能力证明。</p>}
        </article>;
      })}
      {task?.boundary && <p className="text-xs leading-5 text-slate-500">{task.boundary}</p>}
      {task?.usage && <p className="text-xs leading-5 text-slate-500">本次记录输入 {task.usage.inputTokens ?? "—"} / 输出 {task.usage.outputTokens ?? "—"} Tokens{task.usage.cacheHitTokens != null ? `；其中缓存命中 ${task.usage.cacheHitTokens}，已包含在输入中` : ""}。本记录不替代供应商账单。</p>}
    </div>}
  </section>;
}
