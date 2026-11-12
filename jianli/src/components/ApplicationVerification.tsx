"use client";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import type { VerificationReplyQuestion } from "@/lib/verification-reply-draft";
import SourceIdentity, { SourceIdentityDetails } from "./SourceIdentity";
import {
  applicationVerificationSources, createApplicationVerificationSession, initialApplicationVerificationState, verificationFailureMessage, verificationMatchesReport,
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
  const [operation, setOperation] = useState<"read" | "generate">("read");
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
  const pending = task?.status === "pending" || task?.status === "running";
  const analysis = task?.status === "completed" && task.aiStatus === "validated" ? task.analysis : null;
  return <section className="space-y-4" aria-labelledby="verification-title">
    <h3 id="verification-title" className="sr-only">企业材料核验建议</h3>
    {!analysis && !pending && !loading && <label className="flex items-start gap-2 text-sm leading-6">
      <input type="checkbox" className="mt-1.5 shrink-0" checked={consent} onChange={event => setConsent(event.target.checked)} />
      <span>同意将当前及投递时的岗位要求、已授权引用片段发送给 DeepSeek 生成建议，可能产生费用。</span>
    </label>}
    <div className="flex flex-wrap items-center gap-3">
      {!analysis && !pending && !loading && <button type="button" className="btn" disabled={!consent} onClick={() => {
        setOperation("generate");
        setConsent(false);
        void session.generate(consent);
      }}>生成核验建议</button>}
      <button type="button" className="btn-quiet" disabled={loading} onClick={() => {
        setOperation("read");
        void session.load();
      }}>刷新结果</button>
    </div>
    {requirementComparison && requirementComparison.status !== "same" && <details className="text-sm text-amber-900">
      <summary className="cursor-pointer">{requirementComparison.status === "changed" ? "岗位要求已更新，本报告基于投递时版本" : "版本信息不足，无法确认岗位要求是否一致"}</summary>
      {!!requirementComparison.changes.length && <ul className="mt-2">{requirementComparison.changes.map(change => <li key={change}>{change}</li>)}</ul>}
      {!!requirementComparison.missingFields.length && <p>缺少比较依据：{requirementComparison.missingFields.join("、")}</p>}
    </details>}
    {loading ? <p role="status" className="text-sm text-indigo-800">{pending || operation === "generate" ? "正在生成核验建议…" : "正在读取已保存建议…"}</p>
      : error ? <p role="alert" className="text-sm leading-6 text-rose-700">{error}</p>
      : notice ? <p role="status" className="text-sm leading-6 text-amber-800">{notice}</p>
      : !task ? <p className="text-sm text-slate-600">暂无已保存建议。</p>
      : !analysis ? <p role="status" className="text-sm text-amber-800">{verificationFailureMessage(task)}</p> : null}
    {analysis && <div className="space-y-4">
      <p className="text-sm text-slate-600">企业建议 · {task?.createdAt ? new Date(task.createdAt).toLocaleString("zh-CN") : "生成时间未记录"}</p>
      {analysis.items.map(item => {
        const requirement = report.items.find(value => value.requirementId === item.requirementId)!;
        const evidence = applicationVerificationSources(requirement).filter(value => value.citationId && item.citationIds.includes(value.citationId));
        return <article key={item.requirementId} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm leading-6">
          <h4 className="font-semibold">{requirement.requirementTitle || requirement.skill}</h4>
          <div><p className="font-medium text-slate-800">可见支持</p><p className="whitespace-pre-wrap break-words">{item.visibleSupport || "本次授权片段未展示足够支持，需人工核验。"}</p></div>
          <div><p className="font-medium text-amber-800">材料缺口与边界</p><p className="whitespace-pre-wrap break-words">{item.informationGap}</p></div>
          <div><p className="font-medium text-slate-800">建议人工核验的问题</p><ol className="list-decimal space-y-2 pl-5">{item.verificationQuestions.map((question, index) => <li key={index} className="whitespace-pre-wrap break-words">{question}{onUseQuestion && <button type="button" className="btn-secondary btn-compact ml-2" onClick={() => onUseQuestion({ requirementId: item.requirementId, requirementIndex: report.items.indexOf(requirement), requirementTitle: requirement.requirementTitle || requirement.skill, question, citationIds: item.citationIds })}>加入回复草稿</button>}</li>)}</ol></div>
          {item.nextStep && <div className="rounded-lg bg-slate-50 p-3"><p className="font-medium">可选下一步：{NEXT_STEP[item.nextStep]}</p><p className="whitespace-pre-wrap break-words">{item.nextStepReason}</p></div>}
          {evidence.length ? <details><summary className="cursor-pointer text-indigo-700">引用来源（{evidence.length}）</summary><div className="space-y-3 pt-2">{evidence.map((source, index) => <div key={`${source.citationId}:${index}`} className="text-sm leading-6"><p><SourceIdentity source={source} materials={report.materials} compact/> · 第{source.lineStart}—{source.lineEnd}行</p>{source.provenance === "reference" && <p className="text-amber-800">参考材料，不构成学生本人实践证明。</p>}<pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2">{source.snippet}</pre><p className="mt-1 text-slate-500">{source.contextNote}</p><SourceIdentityDetails source={source}/></div>)}</div></details> : <p className="text-sm text-slate-600">本项没有对应引用。</p>}
        </article>;
      })}
    </div>}
  </section>;
}
