"use client";
import { useState } from "react";
import type { ApplicationView } from "@/lib/api/client";
import { comparableRadarAxes } from "@/lib/application-comparison";
import { radarPosition, radarPointKind, radarScore, radarSegments, RADAR_STATUS } from "@/lib/skill-radar";
import { reportModeLabel } from "@/lib/report-display";
import { requirementSummary } from "@/lib/report-workspace";
import { heatmapCellClass } from "@/lib/heatmap-cell.js";
import SourceIdentity, { SourceIdentityDetails } from "./SourceIdentity";

export default function CandidatePairComparison({candidates, busy, onOpen, initialIds, onRequirementChange}:{
  candidates: [ApplicationView, ApplicationView]; busy: boolean; onOpen:()=>void;
  initialIds?: string[]; onRequirementChange?:(id:string,side:number)=>void;
}) {
  const [selectedId,setFirst]=useState(initialIds?.[0]||candidates[0].dimensions[0]?.requirementId||"");
  const [secondId,setSecond]=useState(initialIds?.[1]||candidates[1].dimensions[0]?.requirementId||"");
  const setSelectedId=(id:string)=>{setFirst(id);onRequirementChange?.(id,0);};
  const setSecondId=(id:string)=>{setSecond(id);onRequirementChange?.(id,1);};
  const aligned=comparableRadarAxes(...candidates);
  const axes=candidates[0].dimensions;
  const current=axes.find(d=>d.requirementId===selectedId)??axes[0];
  const colors=["#4f46e5","#c2410c"];
  const ready=candidates.every(c=>c.report?.id===c.reportId);
  return <section className="panel pair-evidence-workspace min-w-0 space-y-4" aria-label="双人证据对照">
    <h2 className="text-xl font-semibold">双人证据对照</h2>
    {!ready?<div className="space-y-3 rounded-xl bg-slate-50 p-4"><p className="text-sm">打开这两份固定报告后查看雷达和引用。仅核对所选两位，不加载其他候选人的报告。</p><button type="button" className="btn" disabled={busy} onClick={onOpen}>打开两份授权报告</button></div>:<>
      {!aligned&&<p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">比较依据不同：岗位要求、权重或规则尺度不一致，不叠加雷达。请分别选择各自报告中的要求核对。</p>}
      {aligned&&<>
        <div className="flex flex-wrap gap-2" aria-label="双人共同岗位要求">{axes.map((d,i)=><button key={d.requirementId} type="button" className={current?.requirementId===d.requirementId?"btn":"btn-secondary"} aria-pressed={current?.requirementId===d.requirementId} onClick={()=>setSelectedId(d.requirementId)}>{i+1} · {d.skill||d.title}</button>)}</div>
      </>}
      {aligned && current && <div className="border-b border-slate-200 pb-3"><h3 className="text-lg font-semibold">{current.title}</h3><p className="mt-1 text-sm text-slate-600">岗位权重 {current.weight} · 投递时固定报告</p></div>}
      <div className="pair-reading-grid grid min-w-0 items-start gap-5">
        <div className="min-w-0"><div className="grid min-w-0 gap-4 md:grid-cols-2">{candidates.map((c,i)=><EvidenceColumn key={c.id} candidate={c} color={colors[i]} requirementId={aligned?current?.requirementId??"":i===0?selectedId:secondId} independent={!aligned} onSelect={i===0?setSelectedId:setSecondId}/>)}</div></div>
        {aligned && <aside className="min-w-0 rounded-xl bg-slate-50 p-3" aria-label="材料支持度辅助概览"><h3 className="text-sm font-semibold">材料支持度</h3><ul className="mt-2 space-y-1 text-sm" aria-label="候选人图例">{candidates.map((c,i)=><li key={c.id} className="break-words"><span className="mr-2 inline-block h-3 w-3 rounded-full" style={{backgroundColor:colors[i]}} aria-hidden="true"/>{c.candidateName}</li>)}</ul>{axes.length>=3&&axes.length<=8?<svg viewBox="0 0 400 400" className="mx-auto w-full max-w-[17rem]" role="group" aria-label="双人同轴材料支持度雷达">
          {[25,50,75,100].map(v=><g key={v}><circle cx="200" cy="200" r={108*v/100} fill="none" stroke="#e2e8f0"/><text x="204" y={200-108*v/100-4} fontSize="10" fill="#64748b">{v}</text></g>)}
          {axes.map((d,i)=>{const end=radarPosition(i,axes.length,1),raw=radarPosition(i,axes.length,1.6),label={x:Math.max(61,Math.min(339,raw.x)),y:Math.max(30,Math.min(370,raw.y))};return <g key={d.requirementId}><line x1="200" y1="200" x2={end.x} y2={end.y} stroke={current?.requirementId===d.requirementId?"#818cf8":"#cbd5e1"}/><g role="button" tabIndex={0} aria-label={`对照要求：${d.skill||d.title}`} aria-pressed={current?.requirementId===d.requirementId} className="cursor-pointer" onClick={()=>setSelectedId(d.requirementId)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setSelectedId(d.requirementId);}}}><rect x={label.x-58} y={label.y-18} width="116" height="36" rx="8" fill={current?.requirementId===d.requirementId?"#eef2ff":"white"} stroke="#e2e8f0"/><text x={label.x} y={label.y+4} textAnchor="middle" fontSize="12" fill="#334155">{Array.from(d.skill||d.title).slice(0,10).join("")}</text></g></g>;})}
          {candidates.map((c,ci)=>{const dims=axes.map(d=>c.dimensions.find(v=>v.requirementId===d.requirementId)!);return <g key={c.id} aria-label={`${c.candidateName}的材料支持度`}>
            {radarSegments(dims).map(([a,b])=>{const start=radarPosition(a,axes.length,radarScore(dims[a])!/100),end=radarPosition(b,axes.length,radarScore(dims[b])!/100);return <line key={`${a}:${b}`} x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke={colors[ci]} strokeWidth="2" strokeDasharray={ci?"5 3":undefined}/>;})}
            {dims.map((d,i)=>{const kind=radarPointKind(d);if(kind==="none")return null;const p=radarPosition(i,axes.length,radarScore(d)!/100);return <g key={d.requirementId} role="button" tabIndex={0} className="cursor-pointer" aria-label={`${c.candidateName} · ${d.skill||d.title} · ${RADAR_STATUS[d.verdict]} · ${radarScore(d)}`} onClick={()=>setSelectedId(d.requirementId)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setSelectedId(d.requirementId);}}}><circle cx={p.x} cy={p.y} r={ci?5:7} fill={kind==="claimed"?"white":colors[ci]} stroke={colors[ci]} strokeWidth="2"/><title>{c.candidateName} · {RADAR_STATUS[d.verdict]} · 材料支持度 {radarScore(d)}</title></g>;})}
          </g>;})}
        </svg>:<p className="text-sm text-slate-600">要求少于3项或超过8项，直接查看逐项证据，避免轴标签拥挤。</p>}
        <p className="text-xs leading-5 text-slate-600">线色表示候选人，不表示证据等级。仅连接相邻且有证据的点；缺材料和不可评不绘点，不代表能力零分。</p>
</aside>}
      </div>
    </>}
  </section>;
}

export function EvidenceColumn({candidate,color,requirementId,independent,onSelect}:{candidate:ApplicationView;color:string;requirementId:string;independent:boolean;onSelect:(id:string)=>void}) {
  const report=candidate.report;
  const item=report?.items.find(d=>d.requirementId===requirementId);
  const useAi=!!item&&item.aiStatus==="validated"&&!report?.aiFallbackUsed;
  const explanation=(useAi?item?.aiExplanation:null)||item?.explanation||"";
  const gap=(useAi?item?.aiInformationGap:null)||item?.evidenceLevelGap||"请核对来源覆盖范围、运行记录与本人贡献；本报告未独立认证。";
  return <article className="min-w-0 space-y-3 rounded-xl border border-slate-200 p-4" aria-label={`${candidate.candidateName}的固定证据`}>
    <h3 className="break-words font-semibold" style={{color}}>{candidate.candidateName}</h3>
    {report&&<p className="text-xs text-slate-600">{reportModeLabel(report)}</p>}
    {independent&&<label className="block text-sm">{candidate.candidateName}的岗位要求<select className="field mt-1" value={requirementId} onChange={e=>onSelect(e.target.value)}>{candidate.dimensions.map(d=><option key={d.requirementId} value={d.requirementId}>{d.skill||d.title}</option>)}</select></label>}
    {item?<>
      {independent && <p className="break-words text-base font-medium">{item.requirementTitle || item.skill}</p>}
      <div className={`rounded-lg border p-3 text-sm ${heatmapCellClass(item.verdict)}`}><strong>{RADAR_STATUS[item.verdict]??item.verdict}</strong><span className="ml-3">材料支持度 {item.finalScore??"不可评"}</span></div>
      <p className="break-words text-base leading-7">{useAi&&item.aiExplanation?`${explanation.slice(0,100)}${explanation.length>100?"…":""}`:requirementSummary(item)}</p>
      <details className="text-sm"><summary className="cursor-pointer py-1 text-indigo-700">完整判断与核验说明</summary><p className="mt-2 break-words leading-6">{explanation}</p><p className="mt-2 break-words leading-6">{gap}</p></details>
      {item.evidenceList.length?<ul className="space-y-3">{item.evidenceList.map((source,index)=><li key={`${source.citationId}:${index}`} className="min-w-0 border-t border-slate-100 pt-3"><p className="text-xs leading-6"><SourceIdentity source={source} materials={report?.materials} compact/> · 第{source.lineStart}–{source.lineEnd}行 · {source.citationId||"规则来源"}</p><details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-indigo-700">展开源码片段</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 text-xs">{source.snippet}</pre><SourceIdentityDetails source={source}/></details>{source.contextComplete===false&&<p className="mt-2 text-xs text-amber-900">{source.contextNote||"引用上下文不完整，需核对完整来源。"}</p>}</li>)}</ul>:<p className="text-sm text-slate-600">当前授权报告没有对应引用，不能据此推断候选人没有该能力。</p>}
    </>:<p className="text-sm text-slate-600">当前授权报告没有对应要求，请按该报告的固定要求核对。</p>}
  </article>;
}
