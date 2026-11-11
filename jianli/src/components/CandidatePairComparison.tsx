"use client";
import { displayMaterialTitle } from "@/lib/demo-display-identity.js";
import IdentityName from "./IdentityName";
import { identityLabel } from "@/lib/demo-display-identity.js";
import { useState } from "react";
import type { ApplicationView } from "@/lib/api/client";
import { comparableRadarAxes, requirementDifference } from "@/lib/application-comparison";
import { radarPosition, radarPointKind, radarSegments, radarRequirementLabels, RADAR_STATUS } from "@/lib/skill-radar";
import { resolveSupportScale, supportMeasure, supportScaleNote, type SupportScale } from "@/lib/support-index.js";
import SupportMeasureDetails from "./SupportMeasureDetails";
import { reportModeLabel } from "@/lib/report-display";
import { requirementConclusion } from "@/lib/report-workspace";
import { heatmapCellClass } from "@/lib/heatmap-cell.js";
import { SourceIdentityDetails } from "./SourceIdentity";
import { invalidNarrativeCitations } from "@/lib/report-citations";
import { compactSourceLabel } from "@/lib/source-label";
import { sourceLimit } from "@/lib/source-limits";
import ReportNarrative from "./ReportNarrative";
import EvidenceSnippet from "./EvidenceSnippet";

export default function CandidatePairComparison({candidates, busy, onOpen, initialIds, onRequirementChange}:{
  candidates: [ApplicationView, ApplicationView]; busy: boolean; onOpen:()=>void;
  initialIds?: string[]; onRequirementChange?:(id:string,side:number)=>void;
}) {
  const [selectedId,setFirst]=useState(initialIds?.[0]||candidates[0].dimensions[0]?.requirementId||"");
  const [secondId,setSecond]=useState(initialIds?.[1]||candidates[1].dimensions[0]?.requirementId||"");
  const setSelectedId=(id:string)=>{setFirst(id);onRequirementChange?.(id,0);};
  const setSecondId=(id:string)=>{setSecond(id);onRequirementChange?.(id,1);};
  const aligned=comparableRadarAxes(...candidates);
  const scale=resolveSupportScale(candidates.flatMap(c=>c.dimensions));
  const overlay=aligned&&scale.mode==="index";
  const axes=candidates[0].dimensions;
  const labels=radarRequirementLabels(axes);
  const current=axes.find(d=>d.requirementId===selectedId)??axes[0];
  const colors=["#4f46e5","#c2410c"];
  const ready=candidates.every(c=>c.report?.id===c.reportId);
  const firstItem = candidates[0].report?.items.find(item => item.requirementId === current?.requirementId);
  const secondItem = candidates[1].report?.items.find(item => item.requirementId === current?.requirementId);
  const comparableSupport = overlay && !!firstItem && !!secondItem && [firstItem, secondItem].every(item =>
    supportMeasure({ score: item.finalScore, verdict: item.verdict, formulaVersion: item.formulaVersion }, scale).ratio != null,
  );
  return <section className="comparison-document workspace-sheet space-y-3" aria-label="双人证据对照">
    <h2 className="section-title">同一要求下的材料证据</h2>
    {!ready?<button type="button" className="btn" disabled={busy} onClick={onOpen}>打开两份授权报告</button>:<>
      {!aligned&&<p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{candidates.some(c=>c.fixedRequirementBasisComplete!==true)?"比较依据不足：历史要求信息不完整，不能确认同一尺度。":"比较依据不同：岗位要求、权重或规则尺度不一致。"}不叠加雷达，请分别核对固定要求。</p>}
      {aligned&&!overlay&&<p role="status" className="text-sm text-amber-900">比较尺度未确认，不叠加雷达。{scale.reason}下方按同一要求核对原报告。</p>}
      {aligned&&<>
        <div className="review-view-nav" aria-label="双人共同岗位要求">{axes.map(d=><button key={d.requirementId} type="button" aria-pressed={current?.requirementId===d.requirementId} onClick={()=>setSelectedId(d.requirementId)}>{labels.get(d.requirementId)?.label}</button>)}</div>
      </>}
      {aligned && current && <div className="comparison-current-requirement border-b border-slate-200 pb-3"><h3 className="text-lg font-semibold">{current.title}</h3><p className="mt-1 text-sm text-slate-600">岗位权重 {current.weight} · 投递时固定报告</p>{firstItem && secondItem && <div className="pair-difference-flow" aria-label="当前要求的候选人材料差异">
        <div className="pair-difference-requirement"><span>要求</span><strong>{current.skill || current.title}</strong></div>
        <div className="pair-difference-candidates">{candidates.map((candidate, index) => {const item = index === 0 ? firstItem : secondItem; return <div key={candidate.id} className={`pair-difference-candidate ${heatmapCellClass(item.verdict)}`}><IdentityName name={candidate.candidateName} identityId={candidate.candidateId}/><strong>{RADAR_STATUS[item.verdict] ?? item.verdict}</strong><span>{item.evidenceList.length ? `${compactSourceLabel(item.evidenceList[0], candidate.report?.materials).fileName} · 第${item.evidenceList[0].lineStart}–${item.evidenceList[0].lineEnd}行` : "无可定位引用"}</span></div>;})}</div>
        <p className="pair-difference-summary" aria-label="当前要求的可见差异">{requirementDifference(firstItem, secondItem, comparableSupport)}</p>
      </div>}</div>}
      <div className={`grid min-w-0 items-start gap-5 ${overlay?"pair-reading-grid":""}`}>
        <div className="grid min-w-0 gap-5 md:grid-cols-2 md:gap-0 md:divide-x md:divide-slate-200">{candidates.map((c,i)=><EvidenceColumn key={c.id} candidate={c} color={colors[i]} scale={aligned?scale:resolveSupportScale(c.dimensions)} requirementId={aligned?current?.requirementId??"":i===0?selectedId:secondId} independent={!aligned} onSelect={i===0?setSelectedId:setSecondId}/>)}</div>
        {overlay && <aside className="comparison-chart min-w-0" aria-label="材料支持度辅助概览"><h3 className="text-sm font-semibold">{scale.label}</h3><ul className="mt-2 space-y-1 text-sm" aria-label="候选人图例">{candidates.map((c,i)=><li key={c.id} className="break-words"><span className="mr-2 inline-block h-3 w-3 rounded-full" style={{backgroundColor:colors[i]}} aria-hidden="true"/><IdentityName name={c.candidateName} identityId={c.candidateId}/> · {i===0?"实线 / 大圆点":"虚线 / 小圆点"}</li>)}</ul>{axes.length>=3&&axes.length<=8?<svg viewBox="0 0 400 400" className="mx-auto w-full max-w-[400px]" role="group" aria-label="双人同轴材料支持度雷达">
          {[25,50,75,100].map(v=><g key={v}><circle cx="200" cy="200" r={108*v/100} fill="none" stroke="#e6eaf1" strokeWidth="0.8"/><text x="204" y={200-108*v/100-4} fontSize="12" fill="#64748b">{v}</text></g>)}
          <text x="204" y="212" fontSize="12" fill="#64748b">0</text>
          {axes.map((d,i)=>{const end=radarPosition(i,axes.length,1),raw=radarPosition(i,axes.length,1.6),label={x:Math.max(61,Math.min(339,raw.x)),y:Math.max(30,Math.min(370,raw.y))};return <g key={d.requirementId}><line x1="200" y1="200" x2={end.x} y2={end.y} stroke={current?.requirementId===d.requirementId?"#aaa5d8":"#e0e5ee"} strokeWidth={current?.requirementId===d.requirementId?1.2:0.8}/><g role="button" tabIndex={0} aria-label={`对照要求：${labels.get(d.requirementId)?.label ?? d.title}`} aria-pressed={current?.requirementId===d.requirementId} className="cursor-pointer" onClick={()=>setSelectedId(d.requirementId)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setSelectedId(d.requirementId);}}}><title>{d.title}</title><rect x={label.x-58} y={label.y-18} width="116" height="36" rx="8" fill={current?.requirementId===d.requirementId?"#eef2ff":"white"} stroke="#e2e8f0"/><text x={label.x} y={label.y+4} textAnchor="middle" fontSize="14" fill="#334155">{labels.get(d.requirementId)?.chart}</text></g></g>;})}
          {candidates.map((c,ci)=>{const dims=axes.map(d=>c.dimensions.find(v=>v.requirementId===d.requirementId)!);return <g key={c.id} aria-label={`${identityLabel(c.candidateName,c.candidateId)}的材料支持度`}>
            {radarSegments(dims,scale).map(([a,b])=>{const start=radarPosition(a,axes.length,supportMeasure(dims[a],scale).ratio!),end=radarPosition(b,axes.length,supportMeasure(dims[b],scale).ratio!);return <line className="radar-data-edge" key={`${a}:${b}`} x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke={colors[ci]} strokeWidth="3.2" strokeLinecap="round" vectorEffect="non-scaling-stroke" strokeDasharray={ci?"7 4":undefined}/>;})}
            {dims.map((d,i)=>{const kind=radarPointKind(d,scale);if(kind==="none")return null;const measure=supportMeasure(d,scale),p=radarPosition(i,axes.length,measure.ratio!);return <g key={d.requirementId} role="button" tabIndex={0} className="cursor-pointer" aria-label={`${identityLabel(c.candidateName,c.candidateId)} · ${labels.get(d.requirementId)?.label ?? d.title} · ${RADAR_STATUS[d.verdict]} · ${measure.text}`} onClick={()=>setSelectedId(d.requirementId)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setSelectedId(d.requirementId);}}}><circle cx={p.x} cy={p.y} r={ci?5:7} fill={kind==="claimed"?"white":colors[ci]} stroke={colors[ci]} strokeWidth="2.5" vectorEffect="non-scaling-stroke"/><title>{identityLabel(c.candidateName,c.candidateId)} · {RADAR_STATUS[d.verdict]} · {scale.label} {measure.text}</title></g>;})}
          </g>;})}
        </svg>:<p className="text-sm text-slate-600">要求少于3项或超过8项，直接查看逐项证据，避免轴标签拥挤。</p>}
        <p className="text-xs leading-5 text-slate-600">线色表示候选人，不表示证据等级。仅连接相邻且有证据的点；缺材料和不可评不绘点。</p>
        <details className="mt-2 text-sm text-slate-600"><summary className="cursor-pointer">指数换算依据</summary><p className="mt-1 leading-6">{supportScaleNote(scale)}</p></details>
</aside>}
      </div>
    </>}
  </section>;
}

export function EvidenceColumn({candidate,color,requirementId,independent,onSelect,scale=resolveSupportScale(candidate.dimensions)}:{candidate:ApplicationView;color:string;requirementId:string;independent:boolean;onSelect:(id:string)=>void;scale?:SupportScale}) {
  const report=candidate.report;
  const item=report?.items.find(d=>d.requirementId===requirementId);
  const invalid=item?invalidNarrativeCitations(item):[];
  const useAi=!!item&&item.aiStatus==="validated"&&!report?.aiFallbackUsed&&!invalid.length;
  const explanation=(useAi?item?.aiExplanation:null)||item?.explanation||"";
  const gap=(useAi?item?.aiInformationGap:null)||item?.evidenceLevelGap;
  const axis=item?{score:item.finalScore,verdict:item.verdict,formulaVersion:item.formulaVersion}:null;
  const measure=axis?supportMeasure(axis,scale):null;
  return <article className="comparison-evidence-column min-w-0 space-y-3 border-t border-slate-200 pt-4 md:border-t-0 md:pt-0 md:first:pr-4 md:last:pl-4" aria-label={`${identityLabel(candidate.candidateName,candidate.candidateId)}的固定证据`}>
    <h3 className="comparison-candidate-name break-words font-semibold" style={{color}}><IdentityName name={candidate.candidateName} identityId={candidate.candidateId}/></h3>
    {report&&<p className="break-words text-sm leading-6 text-slate-600">{reportModeLabel(report) ? `${reportModeLabel(report)} · ` : ""}{report.materials.length ? report.materials.map(m=>`${displayMaterialTitle(m.title, m.id)} v${m.versionNumber}`).join(" · ") : "材料版本未记录"}</p>}
    {independent&&<label className="block text-sm"><IdentityName name={candidate.candidateName} identityId={candidate.candidateId}/>的岗位要求<select className="field mt-1" value={requirementId} onChange={e=>onSelect(e.target.value)}>{Array.from(radarRequirementLabels(candidate.dimensions), ([id, label])=><option key={id} value={id}>{label.label}</option>)}</select></label>}
    {item?<>
      {independent && <p className="break-words text-base font-medium">{item.requirementTitle || item.skill}</p>}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <strong className={`rounded border px-2 py-1 text-sm ${heatmapCellClass(item.verdict)}`}>{RADAR_STATUS[item.verdict]??item.verdict}</strong>
        {measure?.ratio!=null&&<span className="text-sm text-slate-700">{scale.label} {measure.text}</span>}
      </div>
      {measure?.issue&&item.verdict!=="unsupported"&&<p role="status" className="text-sm text-amber-900">{measure.issue}；原始值 {String(measure.raw??"未记录")}。</p>}
      {invalid.length>0&&<p className="text-sm text-amber-900">历史AI解释含未对齐引用，当前按规则判断与固定来源核对。</p>}
      <p className="break-words text-base leading-7">{useAi&&report?<ReportNarrative text={explanation} item={item} report={report} sourcePrefix={`pair-${candidate.id}-`}/>:requirementConclusion(item)}</p>
      {item.evidenceList.length?<ul className="space-y-2">{item.evidenceList.map((source,index)=>{const limit=report?sourceLimit(report,source):null;return <li key={`${source.citationId}:${index}`} className="comparison-source min-w-0 border-t border-slate-100 pt-2"><details id={`pair-${candidate.id}-citation-${source.citationId??index}`} open={index===0} className="text-sm"><summary className="cursor-pointer py-2 text-indigo-700">{compactSourceLabel(source,report?.materials).fileName} · 第{source.lineStart}–{source.lineEnd}行{limit?` · ${limit.label}`:""}</summary>{limit&&<p className="text-sm leading-6 text-amber-900">{limit.detail}</p>}{limit?.readable!==false&&<EvidenceSnippet evidence={source} materials={report?.materials} showContextNote={false}/>}<SourceIdentityDetails source={source}/></details>{source.provenance==="reference"&&<p className="text-sm text-amber-900">第三方参考，不作为本人实践证明。</p>}</li>;})}</ul>:<p className="text-sm text-slate-600">当前授权报告没有对应引用，不能据此推断候选人没有该能力。</p>}
      {gap&&<p className="break-words text-base leading-7 text-slate-700">报告缺口：{gap}</p>}
      <details className="text-sm"><summary className="disclosure">原报告判断记录</summary>
        <SupportMeasureDetails raw={item.finalScore} formulaVersion={item.formulaVersion} scale={scale}/>
        <p className="mt-2 break-words leading-6">{useAi?item.aiExplanation:item.explanation}</p>
      </details>
    </>:<p className="text-sm text-slate-600">当前授权报告没有对应要求，请按该报告的固定要求核对。</p>}
  </article>;
}
