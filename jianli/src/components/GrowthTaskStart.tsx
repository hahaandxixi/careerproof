"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import type { EnterpriseReplyContext as ReplyContext, GrowthPlan } from "@/lib/api/domain";
import { adoptGrowthAdvice, type GrowthAdviceDraft } from "@/lib/analysis-status";
import EvidenceLink from "./EvidenceLink";
import EnterpriseReplyContext from "./EnterpriseReplyContext";

export default function GrowthTaskStart({ reportId, requirementId, advice }: { reportId: string; requirementId: string; advice?: GrowthAdviceDraft | null }) {
  const router = useRouter();
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [open, setOpen] = useState(false);
  const [replyContext, setReplyContext] = useState<ReplyContext | null>(null);
  const [replyContextError, setReplyContextError] = useState("");
  const [existingId, setExistingId] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [lookupError, setLookupError] = useState("");
  const [lookupRevision, setLookupRevision] = useState(0);
  useEffect(() => {
    const openFromAnchor = () => {
      if (window.location.hash === `#growth-${requirementId}` || new URLSearchParams(window.location.search).get("enterpriseReply") === requirementId) setOpen(true);
    };
    openFromAnchor();
    window.addEventListener("hashchange", openFromAnchor);
    return () => window.removeEventListener("hashchange", openFromAnchor);
  }, [requirementId]);
  useEffect(() => {
    if (!open) return;
    let active = true; setChecked(false); setLookupError(""); setExistingId(null);
    setReplyContext(null); setReplyContextError("");
    void api.existingGrowthTask(reportId, requirementId).then(result => {
      if (active) { setExistingId(result?.id || null); setChecked(true); }
    }).catch(reason => { if (active) setLookupError(errorMessage(reason)); });
    void api.enterpriseReplyContext(reportId, requirementId).then(result => {
      if (active) setReplyContext(result);
    }).catch(reason => { if (active) setReplyContextError(errorMessage(reason)); });
    return () => { active = false; };
  }, [open, reportId, requirementId, lookupRevision]);
  const [kind, setKind] = useState<GrowthPlan["gapKind"]>("implementation");
  const [kindEdited, setKindEdited] = useState(false);
  const [deliverable, setDeliverable] = useState("");
  const [steps, setSteps] = useState("");
  const [checks, setChecks] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try {
      const result = await api.createGrowthTask(reportId, { requirementId, gapKind: kind, deliverable,
        steps: steps.split("\n").map(v => v.trim()).filter(Boolean),
        acceptanceChecks: checks.split("\n").map(v => v.trim()).filter(Boolean) });
      if (mounted.current) router.push(`/growth/${result.id}`);
    } catch (reason) { if (mounted.current) setError(errorMessage(reason)); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <div className="mt-4 rounded-xl border border-indigo-200 p-4 text-sm">
    <button type="button" aria-expanded={open} className="text-indigo-700 underline" onClick={() => setOpen(v => !v)}>{open ? "收起补证任务" : "从这条缺口创建或打开补证任务"}</button>
    {open && replyContext && <div className="mt-3"><EnterpriseReplyContext context={replyContext} /></div>}
    {open && replyContextError && <p role="status" className="mt-3 text-xs text-amber-800">企业回复上下文暂无法读取：{replyContextError}。仍可按原报告创建任务。</p>}
    {open && !checked && !lookupError && <p role="status" className="mt-3">正在读取该缺口已有任务，不调用模型…</p>}
    {open && lookupError && <div role="alert" className="mt-3 text-rose-700">{lookupError}<button className="ml-3 underline" onClick={() => setLookupRevision(value => value + 1)}>重新读取任务</button></div>}
    {open && checked && existingId && <p className="mt-3"><Link className="text-indigo-700 underline" href={`/growth/${existingId}`}>打开这条缺口已有补证任务 →</Link><span className="mt-2 block text-xs text-slate-600">沿用已保存的交付物和固定基准，无需重新填写；继续补证请从新报告创建下一任务。</span></p>}
    {open && checked && !existingId && <form className="mt-4 space-y-3" onSubmit={submit}>
      <p className="text-xs leading-6 text-slate-600">结合上方缺口填写可交付材料。保存固定基准，不调用模型；同一报告同一要求已有任务时会打开原任务。任务完成不直接提升等级。</p>
      {advice && <div className="space-y-2 rounded-lg bg-indigo-50 p-3 text-xs leading-6 text-indigo-950">
        <p className="font-medium">这条要求已保存的 AI 补证建议</p>
        <p>{advice.suggestion}</p>
        <p>仍需核对：{advice.gap}</p>
        <div className="flex flex-wrap gap-3">{advice.citationIds.map(id => <EvidenceLink key={id} citationId={id} className="text-indigo-700 underline">核对引用 {id}</EvidenceLink>)}</div>
        {advice.taskPlan && <div className="space-y-1 rounded-lg border border-indigo-100 bg-white p-3">
          <p className="font-medium">AI 可编辑任务草稿</p>
          <p>交付物：{advice.taskPlan.deliverable}</p>
          <p>执行步骤：{advice.taskPlan.steps.join("；")}</p>
          <p>核验条件：{advice.taskPlan.acceptanceChecks.join("；")}</p>
        </div>}
        <p>建议已通过程序校验，是否适合作为任务仍需本人核对。采用只补入空白项，保留已填写内容和手动选择的类型；不会保存任务或调用模型。</p>
        {(!deliverable.trim() || (advice.taskPlan && (!steps.trim() || !checks.trim()))) && <button type="button" className="text-indigo-700 underline" disabled={busy} onClick={() => {
          const draft = adoptGrowthAdvice({ kind, kindEdited, deliverable, steps, checks }, advice);
          setDeliverable(draft.deliverable); setSteps(draft.steps); setChecks(draft.checks);
          setKind(draft.kind); setError("");
        }}>{advice.taskPlan ? "补入 AI 任务草稿中的空白项" : "采用建议作为可编辑交付物草稿"}</button>}
      </div>}
      <fieldset disabled={busy} className="space-y-3">
        <label className="block">缺口类型<select className="field mt-1" value={kind} onChange={e => { setKind(e.target.value as GrowthPlan["gapKind"]); setKindEdited(true); }}><option value="implementation">缺少实现或当前实现待核验</option><option value="execution">缺少运行结果</option><option value="contribution">缺少本人贡献记录</option><option value="review">修正复核指出的问题</option></select></label>
        <label className="block">具体交付物<textarea className="field mt-1" rows={3} required maxLength={1000} value={deliverable} onChange={e => setDeliverable(e.target.value)} placeholder="例如：SQL 查询脚本及脱敏的查询结果样例" /></label>
        <label className="block">执行步骤（每行一项，最多5项）<textarea className="field mt-1" rows={4} required maxLength={5000} value={steps} onChange={e => setSteps(e.target.value)} /></label>
        <label className="block">核验条件（每行一项，最多5项）<textarea className="field mt-1" rows={4} required maxLength={5000} value={checks} onChange={e => setChecks(e.target.value)} /></label>
        <button className="btn" disabled={busy}>{busy ? "保存任务…" : "保存并进入补证"}</button>
      </fieldset>
      {error && <p role="alert" className="text-rose-700">{error}</p>}
    </form>}
  </div>;
}
