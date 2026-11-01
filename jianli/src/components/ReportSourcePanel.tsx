"use client";
import { useEffect, useState } from "react";
import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { adoptedReportExplanation } from "@/lib/report-workspace";
import { compactSourceLabel, sourceLocationId } from "@/lib/source-label";
import EvidenceSnippet from "./EvidenceSnippet";
import { SourceIdentityDetails } from "./SourceIdentity";
import { sourceLimit } from "@/lib/source-limits";

export default function ReportSourcePanel({ report, item }: { report: MatchReport; item: ReportItem }) {
  const adopted = !!adoptedReportExplanation(report, item);
  const first = adopted ? item.evidenceList.findIndex(source => !!source.citationId && item.aiCitationIds.includes(source.citationId)) : 0;
  const [entry,setEntry]=useState({index:Math.max(0,first),anchor:"",revision:0});
  const selected=Math.min(entry.index,Math.max(0,item.evidenceList.length-1));
  useEffect(()=>{
    const selectAnchor=(anchor:string)=>{
      const index=item.evidenceList.findIndex((source,i)=>sourceLocationId(item.requirementId,source,i)===anchor);
      if(index>=0)setEntry(old=>({index,anchor,revision:old.revision+1}));
    };
    const location=()=>{try{selectAnchor(decodeURIComponent(window.location.hash.slice(1)));}catch{/* Invalid historical fragments do not identify a source. */}};
    const click=(event:MouseEvent)=>{
      if(event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
      const href=event.target instanceof Element?event.target.closest('a[href]')?.getAttribute('href'):null;
      if(href?.startsWith('#')){try{selectAnchor(decodeURIComponent(href.slice(1)));}catch{/* Keep the current source. */}}
    };
    location();window.addEventListener('hashchange',location);window.addEventListener('popstate',location);document.addEventListener('click',click,true);
    return()=>{window.removeEventListener('hashchange',location);window.removeEventListener('popstate',location);document.removeEventListener('click',click,true);};
  },[item]);
  useEffect(()=>{
    if(!entry.anchor)return;
    const frame=requestAnimationFrame(()=>document.getElementById(entry.anchor)?.scrollIntoView({block:'start'}));
    return()=>cancelAnimationFrame(frame);
  },[entry]);
  const choose=(index:number)=>setEntry(old=>({index,anchor:"",revision:old.revision+1}));
  const identities = new Set(item.evidenceList.map(source=>compactSourceLabel(source,report.materials).material));
  return <section className="min-w-0" aria-label={`${item.skill}的证据来源`}>
    <h4 className="font-semibold">来源（{item.evidenceList.length}）</h4>
    {identities.size===1&&<p className="mt-1 text-sm text-slate-600">{[...identities][0]}</p>}
    {item.evidenceList.length>1&&<div className="mt-3 flex min-w-0 items-end gap-2">
      <label className="min-w-0 flex-1 text-sm">选择来源<select className="field mt-1 w-full min-w-0" value={selected} onChange={event=>choose(Number(event.target.value))}>
        {item.evidenceList.map((source,index)=>{const label=compactSourceLabel(source,report.materials);return <option key={sourceLocationId(item.requirementId,source,index)} value={index}>{index+1}. {label.fileName} · {source.lineStart}–{source.lineEnd}行 · {label.material}</option>;})}
      </select></label>
      <button type="button" className="btn-quiet shrink-0" aria-label="上一个来源" disabled={selected===0} onClick={()=>choose(selected-1)}>上一处</button>
      <button type="button" className="btn-quiet shrink-0" aria-label="下一个来源" disabled={selected===item.evidenceList.length-1} onClick={()=>choose(selected+1)}>下一处</button>
    </div>}
    {item.evidenceList.length ? <div className="mt-3">{item.evidenceList.map((source, index) => {
      const label = compactSourceLabel(source, report.materials);
      const limit = sourceLimit(report, source);
      return <article key={sourceLocationId(item.requirementId,source,index)} hidden={selected!==index} aria-label={`来源 ${index+1}：${label.fileName}`} className="rounded-lg border border-indigo-200">
        <header className="p-3 text-base text-indigo-900"><strong>{label.fileName}</strong><span className="ml-2 text-sm">第 {source.lineStart}–{source.lineEnd} 行</span>{limit && <span className="ml-2 text-sm text-amber-900">{limit.label}</span>}{(identities.size>1||source.provenance==="reference")&&<span className="mt-1 block text-sm text-slate-600">{identities.size>1?label.material:""}{source.provenance === "reference" ? " · 第三方参考，不计评级" : ""}</span>}</header>
        <div id={sourceLocationId(item.requirementId, source, index)} className="min-w-0 scroll-mt-24 px-3 pb-3">
          {limit && <p className="mb-2 text-sm leading-6 text-amber-900">{limit.detail}</p>}
          {limit?.readable !== false && <EvidenceSnippet evidence={source} materials={report.materials} showContextNote={false} />}
          <details className="mt-2 text-sm text-slate-600"><summary className="cursor-pointer py-1">来源说明</summary><p className="mt-2 break-words leading-6">{source.explanation}</p><p className="mt-2">{source.citationId || `规则来源 ${index + 1}`} · {source.contextNote}</p></details>
          <SourceIdentityDetails source={source} />
        </div>
      </article>;
    })}</div> : <p className="mt-3 text-sm leading-7 text-slate-600">{item.verdict === "unsupported" ? "当前规则未覆盖此要求，请人工核对保存材料。" : "当前报告没有对应的可定位引用，不能据此认定没有这项能力。"}</p>}
  </section>;
}
