"use client";

import Link from "next/link";
import { sourceLabel } from "@/lib/source-label";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { ReportComparison } from "@/lib/api/domain";
import { GROWTH_CHANGES as LABELS } from "@/lib/growth-workflow";
import { evidenceLevelName } from "@/lib/evidence-display";
import ReportItemExplanation from "./ReportItemExplanation";

export default function ReportComparisonPanel({ reportId, revision }: { reportId: string; revision: string }) {
  const generation = useRef(0);
  const [value, setValue] = useState<ReportComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { generation.current += 1; setValue(null); setLoaded(false); setError(""); setBusy(false);
    return () => { generation.current += 1; };
  }, [reportId, revision]);
  async function load() {
    const requestGeneration = generation.current;
    setBusy(true); setError("");
    try { const result = await api.previousComparison(reportId); if (requestGeneration === generation.current) { setValue(result); setLoaded(true); } }
    catch (reason) { if (requestGeneration === generation.current) setError(errorMessage(reason)); }
    finally { if (requestGeneration === generation.current) setBusy(false); }
  }
  return <section className="panel space-y-4">
    <div><h2 className="font-semibold">证据变化与补证进度</h2><p className="mt-2 text-sm text-slate-600">与同一岗位最近一份更早的报告比较；读取已有结果，不调用模型。</p></div>
    <button className="btn-secondary" disabled={busy} onClick={load}>{busy ? "读取对比…" : "与上一份报告对比"}</button>
    {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
    {loaded && !value && <p className="text-sm text-slate-500">尚无同一岗位的更早报告。完成补证并重新分析后，可以在新报告中查看变化。</p>}
    {value && <div className="space-y-4 text-sm">
      <div className="flex flex-wrap gap-4"><Link className="text-indigo-700 underline" href={`/reports/${value.baseId}`}>打开基准报告</Link><span>变化背景：{value.contextChanges.map(key => LABELS[key] ?? key).join("、") || "未发现已记录的背景变化"}</span></div>
      <details><summary className="cursor-pointer">两次材料版本清单</summary>{[["基准", value.baseMaterials], ["当前", value.targetMaterials]].map(([label, rows]) => <div key={String(label)} className="mt-2"><strong>{String(label)}</strong><ul className="pl-4">{(rows as ReportComparison["baseMaterials"]).map(m => <li key={`${m.kind}-${m.id}`}>{m.title} · 第 {m.versionNumber} 版</li>)}</ul></div>)}</details>
      {value.items.map(item => <article key={item.requirementId} className="space-y-2 rounded-lg border border-slate-200 p-3">
        <strong>{item.title}</strong>{item.changes.includes("requirement") && <div className="text-xs leading-6 text-slate-600"><p>原要求：{item.baseRequirement?.title ?? "无已保存要求"} · 权重 {item.baseRequirement?.weight ?? "未记录"}</p><p>当前要求：{item.targetRequirement?.title ?? "无已保存要求"} · 权重 {item.targetRequirement?.weight ?? "未记录"}</p></div>}<p>实践证据等级：{item.baseLevel == null ? "未评级" : evidenceLevelName(item.baseLevel)} → {item.targetLevel == null ? "未评级" : evidenceLevelName(item.targetLevel)}</p>
        <p className="text-xs text-slate-600">{item.changes.map(key => LABELS[key] ?? key).join("、") || "未发现已记录的变化"}</p>
        <p className="text-xs text-slate-500">AI 状态：{item.baseAiStatus ?? "无此项"} → {item.targetAiStatus ?? "无此项"}；复核状态：{item.baseReview ?? "无复核"} → {item.targetReview ?? "无复核"}</p>
        <ReportItemExplanation item={item} targetLabel="当前报告" />
        {[["新增展示", item.addedEvidence, reportId], ["不再展示", item.removedEvidence, value.baseId]].map(([label, entries, id]) => <div key={String(label)}><p>{String(label)}：{(entries as typeof item.addedEvidence).length} 条</p><ul>{(entries as typeof item.addedEvidence).map((e, i) => <li key={i} className="break-all"><Link className="text-indigo-700 underline" href={`/reports/${id}${e.citationId ? `#citation-${e.citationId}` : `#requirement-${item.requirementId}`}`}>{sourceLabel(e, String(label) === "新增展示" ? value.targetMaterials : value.baseMaterials)} · 第 {e.lineStart}–{e.lineEnd} 行</Link></li>)}</ul></div>)}
      </article>)}
      <ul className="space-y-1 rounded-lg bg-amber-50 p-3 text-xs leading-6 text-amber-900">{value.limitations.map(note => <li key={note}>{note}</li>)}</ul>
    </div>}
  </section>;
}
