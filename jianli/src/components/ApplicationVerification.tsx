"use client";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import type { VerificationReplyQuestion } from "@/lib/verification-reply-draft";
import SourceIdentity, { SourceIdentityDetails } from "./SourceIdentity";
import {
  applicationVerificationSources, createApplicationVerificationSession, initialApplicationVerificationState, verificationMatchesReport,
} from "@/lib/application-verification-session";

const NEXT_STEP = {
  review_materials: "继续核对已授权材料",
  request_evidence: "向学生提出补证请求",
  discuss_implementation: "人工沟通具体实现",
};

export default function ApplicationVerification({ applicationId, report, onUnavailable, onUseQuestion, requirementComparison }: {
  applicationId: string; report: MatchReport; onUnavailable(): void;
  onUseQuestion?: (question: VerificationReplyQuestion) => void;
  requirementComparison?: {status:"same"|"changed"|"unknown";changes:string[];missingFields:string[]};
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
    <h3 id="verification-title" className="text-lg font-semibold">材料核验建议</h3>
    <p className="text-sm leading-6 text-slate-600">企业另行生成的核验建议，不改变学生原报告。</p>
    {!analysis&&<><label className="flex items-start gap-2 text-sm leading-6">
      <input type="checkbox" className="mt-1.5 shrink-0" checked={consent} disabled={loading} onChange={event => setConsent(event.target.checked)} />
      <span>同意将当前岗位要求、投递时要求与已授权引用片段发送给 DeepSeek 官方 API，生成核验建议，可能产生费用。</span>
    </label>
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" className="btn" disabled={loading || !consent} onClick={() => void session.generate(consent)}>生成建议</button>
      <button type="button" className="text-sm text-indigo-700 underline disabled:text-slate-400" disabled={loading} onClick={() => void session.load()}>读取已保存建议</button>
    </div></>}
    {analysis&&<button type="button" className="min-h-10 text-sm text-indigo-700 underline" disabled={loading} onClick={()=>void session.load()}>刷新已保存建议</button>}
    {requirementComparison?.status!=="same" && <details className="text-sm text-amber-900"><summary className="cursor-pointer">{requirementComparison?.status==="changed" ? "岗位要求已更新，本报告基于投递时版本" : "版本信息不足，无法确认岗位要求是否一致"}</summary><ul className="mt-2">{requirementComparison?.changes.map((s,i)=><li key={i}>{s}</li>)}</ul>{!!requirementComparison?.missingFields.length&&<p>缺少比较依据：{requirementComparison.missingFields.join("、")}</p>}</details>}
    {task?.usageKnown===false&&<p className="text-sm text-amber-900">本次用量收据不完整，已知用量不代表全部费用；未核实部分继续占用预留。</p>}
    {task?.dailyBudget && <details aria-label="今日 AI 预算" className="rounded-lg bg-white p-3 text-sm leading-6 text-slate-700"><summary className="cursor-pointer text-indigo-700">用量详情</summary>
      <p className="font-medium">今日 AI 预算（北京时间）</p>
      <p>已知用量：输入 {task.dailyBudget.knownInputTokens} / 输出 {task.dailyBudget.knownOutputTokens} Tokens</p>
      <p>保守预留：输入上界 {task.dailyBudget.heldInputBound} / 输出上界 {task.dailyBudget.heldOutputBound} Tokens</p>
      <p>待核实收据：{task.dailyBudget.unknownReservationCount} 条；没有可信收据的请求继续占用预留，不算作零用量。</p>
      {(task.dailyBudget.adjustedInputCapacity > 0 || task.dailyBudget.adjustedOutputCapacity > 0) && <p>管理员审计调整容量：输入 {task.dailyBudget.adjustedInputCapacity} / 输出 {task.dailyBudget.adjustedOutputCapacity} Tokens（不等于厂商实际账单）</p>}
      <p>{task.usageKnown === false ? "本次收据不完整；已知部分不代表全部用量。" : "预算展示是当前账目快照；是否可发送仍由服务端逐次准入判断。"}</p>
    </details>}
    {loading && <p role="status" className="text-sm text-indigo-800">{task ? "正在生成核验建议，已授权范围会再次核对…" : "正在核对已保存的核验建议…"}</p>}
    {notice && <p role="status" className="text-sm leading-6 text-amber-800">{notice}</p>}
    {error && <p role="alert" className="text-sm leading-6 text-rose-700">{error}</p>}
    {!loading && !task && !error && <p className="text-sm text-slate-500">尚无已保存的核验建议，可确认外发范围后生成。</p>}
    {task && !loading && task.status === "completed" && !analysis && <p role="status" className="text-sm text-amber-800">{task.failureKind === "saved_validation_failed" ? "已保存建议未通过当前固定报告校验，已隐藏。请核对原报告；如需重新生成，请重新确认外发范围。" : "本次没有可展示的有效 AI 建议，请继续核对原报告。"}</p>}
    {analysis && <div className="space-y-4">
      <p className="text-sm text-slate-600">企业建议 · {task?.createdAt ? new Date(task.createdAt).toLocaleString("zh-CN") : "生成时间未记录"}</p>
      {analysis.items.map(item => {
        const requirement = report.items.find(value => value.requirementId === item.requirementId)!;
        const evidence = applicationVerificationSources(requirement).filter(value => value.citationId && item.citationIds.includes(value.citationId));
        return <article key={item.requirementId} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm leading-6">
          <h4 className="font-semibold">{requirement.requirementTitle || requirement.skill}</h4>
          <div><p className="font-medium text-slate-800">可见支持</p><p className="whitespace-pre-wrap break-words">{item.visibleSupport || "本次授权片段未展示足够支持，需人工核验。"}</p></div>
          <div><p className="font-medium text-amber-800">材料缺口与边界</p><p className="whitespace-pre-wrap break-words">{item.informationGap}</p></div>
          <div><p className="font-medium text-slate-800">建议人工核验的问题</p><ol className="list-decimal space-y-2 pl-5">{item.verificationQuestions.map((question, index) => <li key={index} className="whitespace-pre-wrap break-words">{question}{onUseQuestion && <button type="button" className="ml-2 text-indigo-700 underline" onClick={() => onUseQuestion({ requirementId: item.requirementId, requirementIndex: report.items.indexOf(requirement), requirementTitle: requirement.requirementTitle || requirement.skill, question, citationIds: item.citationIds })}>加入回复草稿</button>}</li>)}</ol></div>
          {item.nextStep && <div className="rounded-lg bg-slate-50 p-3"><p className="font-medium">可选下一步：{NEXT_STEP[item.nextStep]}</p><p className="whitespace-pre-wrap break-words">{item.nextStepReason}</p><p className="mt-1 text-xs text-slate-500">由企业自行确认和执行，此建议不会自动发给学生。</p></div>}
          {evidence.length ? <details><summary className="cursor-pointer text-indigo-700">引用来源（{evidence.length}）</summary><div className="space-y-3 pt-2">{evidence.map((source, index) => <div key={`${source.citationId}:${index}`} className="text-sm leading-6"><p><SourceIdentity source={source} materials={report.materials} compact/> · 第{source.lineStart}—{source.lineEnd}行</p>{source.provenance === "reference" && <p className="text-amber-800">参考材料，不构成学生本人实践证明。</p>}<pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2">{source.snippet}</pre><p className="mt-1 text-slate-500">{source.contextNote}</p><SourceIdentityDetails source={source}/></div>)}</div></details> : <p className="text-sm text-slate-600">本项没有支持引用；问题和补证建议不构成能力证明。</p>}
        </article>;
      })}
      <details className="text-sm text-slate-600"><summary className="cursor-pointer">模型与判断范围</summary><p>{task?.aiModel||"DeepSeek"} · {task?.promptVersion}</p>{task?.boundary&&<p>{task.boundary}</p>}{task?.usage&&<p>记录输入 {task.usage.inputTokens??"未知"} / 输出 {task.usage.outputTokens??"未知"} Tokens，不替代供应商账单。</p>}</details>
    </div>}
  </section>;
}
