"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import type { EnterpriseReplyContext as ReplyContext, GrowthPlan, GrowthTask } from "@/lib/api/domain";
import { adoptGrowthAdvice, type GrowthAdviceDraft } from "@/lib/analysis-status";
import EvidenceLink from "./EvidenceLink";
import EnterpriseReplyContext from "./EnterpriseReplyContext";

export default function GrowthTaskStart({ reportId, requirementId, advice, triggerLabel, primary = false, onExistingTask, showExistingPlan = true, compact = false }: { reportId: string; requirementId: string; advice?: GrowthAdviceDraft | null; triggerLabel?: string; primary?: boolean; onExistingTask?: (task: GrowthTask | null) => void; showExistingPlan?: boolean; compact?: boolean }) {
  const router = useRouter();
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [open, setOpen] = useState(false);
  const [replyContext, setReplyContext] = useState<ReplyContext | null>(null);
  const [replyContextError, setReplyContextError] = useState("");
  const [existingTask, setExistingTask] = useState<GrowthTask | null>(null);
  const [checked, setChecked] = useState(false);
  const [lookupError, setLookupError] = useState("");
  const [lookupRevision, setLookupRevision] = useState(0);
  useEffect(() => {
    const openFromAnchor = () => {
      if (window.location.hash === `#growth-${requirementId}` || new URLSearchParams(window.location.search).get("enterpriseReply") === requirementId) setOpen(true);
    };
    // SPA hash navigation need not emit hashchange; a repeated same-fragment
    // click also emits none. Observe the explicit local link, including Enter.
    const openFromLink = (event: MouseEvent) => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (link?.getAttribute("href") === `#growth-${requirementId}`) setOpen(true);
    };
    openFromAnchor();
    window.addEventListener("hashchange", openFromAnchor);
    document.addEventListener("click", openFromLink);
    return () => { window.removeEventListener("hashchange", openFromAnchor); document.removeEventListener("click", openFromLink); };
  }, [requirementId]);
  useEffect(() => {
    if (!open) return;
    let active = true; setChecked(false); setLookupError(""); setExistingTask(null);
    onExistingTask?.(null);
    setReplyContext(null); setReplyContextError("");
    void api.existingGrowthTask(reportId, requirementId).then(result => {
      if (active) { setExistingTask(result); onExistingTask?.(result); setChecked(true); }
    }).catch(reason => { if (active) setLookupError(errorMessage(reason)); });
    void api.enterpriseReplyContext(reportId, requirementId).then(result => {
      if (active) setReplyContext(result);
    }).catch(reason => { if (active) setReplyContextError(errorMessage(reason)); });
    return () => { active = false; };
  }, [open, reportId, requirementId, lookupRevision, onExistingTask]);
  const [kind, setKind] = useState<GrowthPlan["gapKind"]>("implementation");
  const [kindEdited, setKindEdited] = useState(false);
  const [deliverable, setDeliverable] = useState("");
  const [steps, setSteps] = useState("");
  const [checks, setChecks] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function savePlan(plan: GrowthPlan) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try {
      const result = await api.createGrowthTask(reportId, plan);
      if (mounted.current) router.push(`/growth/${result.id}`);
    } catch (reason) { if (mounted.current) setError(errorMessage(reason)); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  function submit(event: React.FormEvent) {
    event.preventDefault();
    return savePlan({ requirementId, gapKind: kind, deliverable,
      steps: steps.split("\n").map(v => v.trim()).filter(Boolean),
      acceptanceChecks: checks.split("\n").map(v => v.trim()).filter(Boolean) });
  }
  return <div className="mt-4 min-w-0 text-sm">
    <button type="button" aria-expanded={open} className={primary ? "btn min-h-11 max-w-full whitespace-normal text-left" : "inline-flex min-h-11 items-center text-indigo-700 underline"} onClick={() => setOpen(v => !v)}>{open ? compact ? "收起补证记录" : "收起补证任务" : existingTask ? existingTask.targetReportId ? "查看补证结果" : compact ? "查看已有补证记录" : "继续补证任务" : triggerLabel ?? "从这条缺口创建或打开补证任务"}</button>
    {open && replyContext && <div className="mt-3"><EnterpriseReplyContext context={replyContext} /></div>}
    {open && replyContextError && <p role="status" className="mt-3 text-xs text-amber-800">企业回复上下文暂无法读取：{replyContextError}。仍可按原报告创建任务。</p>}
    {open && !checked && !lookupError && <p role="status" className="mt-3">正在读取该缺口已有任务，不调用模型…</p>}
    {open && lookupError && <div role="alert" className="mt-3 text-rose-700">{lookupError}<button className="ml-3 underline" onClick={() => setLookupRevision(value => value + 1)}>重新读取任务</button></div>}
    {open && checked && existingTask && <div className="mt-3 space-y-3 text-sm leading-7">
      <Link className={primary ? "btn inline-flex min-h-11 items-center" : "inline-flex min-h-11 items-center text-indigo-700 underline"} href={`/growth/${existingTask.id}`}>{existingTask.targetReportId ? "查看补证结果" : compact ? "查看已有补证记录" : "继续补证任务"} →</Link>
      <p className="text-xs text-slate-600">沿用已保存的交付物和固定基准，无需重新填写；原报告和投递快照不变。</p>
      {showExistingPlan && (existingTask.actionNeedsRecheck || existingTask.taskPlanNeedsRecheck) && <p role="alert" className="text-amber-900">已有任务的建议或计划需要重新核对。{existingTask.taskPlanWarning} 请在任务中核对原始来源，不要直接照旧建议重复上传。</p>}
      {showExistingPlan && <>
      <p className="font-medium">已有任务的交付物：<span className="break-words font-normal">{existingTask.plan.deliverable}</span></p>
      <ol aria-label="已有任务的执行步骤" className="list-decimal space-y-1 pl-5">{existingTask.plan.steps.map((step, index) => <li key={index} className="break-words">{step}</li>)}</ol>
      <details><summary className="cursor-pointer py-2 text-indigo-700">查看已有任务的核验条件</summary><ul className="list-disc space-y-1 pl-5">{existingTask.plan.acceptanceChecks.map((check, index) => <li key={index} className="break-words">{check}</li>)}</ul></details>
      </>}
      {existingTask.targetReportId && <p>已保存新版报告，可从任务中查看逐项变化；原报告仍使用原始材料版本。<Link className="ml-2 text-indigo-700 underline" href={`/reports/${existingTask.targetReportId}`}>打开新版报告 →</Link></p>}
    </div>}
    {open && checked && !existingTask && <div className="mt-4 space-y-3">
      {compact && <div className="space-y-2 text-xs leading-6 text-slate-600">
        <p>没有这项要求的已有记录。可跳过记录，直接复制建议、离站改进和上传新版；自定义计划仅用于需要保存固定基准的情况。</p>
        {advice?.taskPlan ? <><p>可以沿用上方已保存的完整计划，无需重新填表。点击后才创建本人记录，不调用模型、不标记完成。</p><button type="button" className="btn-secondary min-h-11" disabled={busy} onClick={() => {
          if (!advice.taskPlan) return;
          void savePlan({ requirementId, gapKind: advice.suggestedKind, deliverable: advice.taskPlan.deliverable, steps: [...advice.taskPlan.steps], acceptanceChecks: [...advice.taskPlan.acceptanceChecks] });
        }}>{busy ? "记录中…" : "确认记录这条建议"}</button></> : <p>当前建议没有完整的交付物、步骤和核验条件，不会自动填造计划。需要记录时可展开下方高级选项。</p>}
      </div>}
      <details open={!compact} className="border-t border-slate-200 pt-2"><summary className="cursor-pointer py-2 text-sm text-slate-600">自定义补证计划（高级，可跳过）</summary>
      <form className="mt-4 space-y-3" onSubmit={submit}>
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
    </form></details>
      {error && <p role="alert" className="text-rose-700">{error}</p>}
    </div>}
  </div>;
}
