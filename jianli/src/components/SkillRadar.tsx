"use client";
import { useEffect, useId, useState } from "react";
import type { ApplicationView } from "@/lib/api/client";
import type { ReportItem } from "@/lib/api/domain";
import type { SourceMaterial } from "@/lib/source-label";
import EvidenceSnippet from "./EvidenceSnippet";
import SourceIdentity, { SourceIdentityDetails } from "./SourceIdentity";
import { RADAR_STATUS, radarPointKind, radarSegments, radarSelection, radarPosition } from "@/lib/skill-radar";
import { evidenceLevelName } from "@/lib/evidence-display";
import { resolveSupportScale, supportMeasure, supportScaleNote, type SampleScale } from "@/lib/support-index.js";
import SupportMeasureDetails from "./SupportMeasureDetails";
import { invalidNarrativeCitations, readableCitationText } from "@/lib/report-citations";

/** Radar rendering modes share one scale/plotting core.
 * - "full": complete reading panel — title, legend, scale note, requirement buttons, chart and evidence detail.
 * - "overview": chart only, for compact page overview bands; selection, scale notes and evidence
 *   stay with the surrounding page so the chart never carries repeated headers or inner scrolling. */
export type SkillRadarVariant = "full" | "overview";

export default function SkillRadar({ dimensions, items = [], initialRequirementId = "", selectedRequirementId, synthetic = false, sampleScale, materials = [], aiFallbackUsed = false, onRequirementChange, evidenceExpanded, onEvidenceExpandedChange, compact = false, variant }: {
  dimensions: ApplicationView["dimensions"]; items?: ReportItem[]; initialRequirementId?: string; selectedRequirementId?: string; synthetic?: boolean; materials?: readonly SourceMaterial[]; aiFallbackUsed?: boolean;
  onRequirementChange?: (id: string) => void;
  evidenceExpanded?: boolean;
  sampleScale?: SampleScale;
  onEvidenceExpandedChange?: (open: boolean) => void;
  compact?: boolean;
  variant?: SkillRadarVariant;
}) {
  const mode: SkillRadarVariant = variant ?? (compact ? "overview" : "full");
  // The parent may own the requirement id. When it does, the radar only mirrors it;
  // clicks still move the shared id through onRequirementChange, never a second copy.
  const [selectedId, setSelectedId] = useState(selectedRequirementId ?? initialRequirementId);
  const detailId = useId();
  const externalId = selectedRequirementId ?? initialRequirementId;
  useEffect(() => { setSelectedId(previous => previous === externalId ? previous : externalId); }, [externalId]);
  const selectRequirement = (id: string) => { if (selectedRequirementId === undefined) setSelectedId(id); onRequirementChange?.(id); };
  const { dimension, item } = radarSelection(dimensions, selectedId, items);
  if (!dimension) return null;
  const selectedIndex = dimensions.indexOf(dimension);
  const point = (index: number, ratio: number) => {
    return radarPosition(index, dimensions.length, ratio);
  };
  const scale = resolveSupportScale(dimensions, synthetic ? sampleScale : undefined);
  const measure = supportMeasure(dimension, scale);
  const useAi = !!item && item.aiStatus==="validated" && !aiFallbackUsed && !invalidNarrativeCitations(item).length;
  const status = (d: typeof dimension) => RADAR_STATUS[d.verdict] ?? "暂不可评";

  const chart = dimensions.length >= 3 && dimensions.length <= 8 ? <svg className={mode === "overview" ? "radar-chart-svg mx-auto w-full" : "mx-auto mt-2 w-full max-w-[440px]"} viewBox="0 0 400 400" role="group" aria-label={`${scale.label}，点选轴标签查看证据`}>
          <circle cx="200" cy="200" r="108" fill="#f8fafc" />
          {[25, 50, 75, 100].map(value => <g key={value}><circle cx="200" cy="200" r={108 * value / 100} fill="none" stroke="#e6eaf1" strokeWidth="0.8" /><text x="204" y={200 - 108 * value / 100 - 4} fill="#94a3b8" fontSize="14">{value}</text></g>)}
          <text x="204" y="212" fill="#94a3b8" fontSize="14">0</text>
          {dimensions.map((d, index) => { const end = point(index, 1); return <line key={d.requirementId} x1="200" y1="200" x2={end.x} y2={end.y} stroke={index === selectedIndex ? "#aaa5d8" : "#e0e5ee"} strokeWidth={index === selectedIndex ? 1.2 : 0.8} />; })}
          {radarSegments(dimensions, scale).map(([a, b]) => {
            const start = point(a, supportMeasure(dimensions[a], scale).ratio!), end = point(b, supportMeasure(dimensions[b], scale).ratio!);
            return <line className="radar-data-edge" key={a} x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="#4f46e5" strokeWidth="3.2" strokeLinecap="round" vectorEffect="non-scaling-stroke" />;
          })}
          {dimensions.map((d, i) => {
            const value = supportMeasure(d, scale);
            const rawLabel = point(i, 1.6), label = {x:Math.max(72,Math.min(328,rawLabel.x)),y:Math.max(30,Math.min(370,rawLabel.y))}, dot = point(i, value.ratio ?? 0);
            const kind = radarPointKind(d, scale), active = i === selectedIndex;
            const title = d.skill || d.title;
            const short = Array.from(title).length > 8 ? Array.from(title).slice(0, 7).join("") + "…" : title;
            return <g key={d.requirementId}>
              {kind !== "none" && <circle cx={dot.x} cy={dot.y} r={active ? 7 : 5} fill={kind === "claimed" ? "white" : d.verdict === "partial" ? "#c7d2fe" : "#4f46e5"} stroke={kind === "claimed" ? "#b66b08" : "#4338ca"} strokeWidth="2.5" vectorEffect="non-scaling-stroke" role="button" tabIndex={0} aria-label={`${title}，${status(d)}，${value.text}，查看证据`} aria-pressed={active} className="cursor-pointer" onClick={() => selectRequirement(d.requirementId)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectRequirement(d.requirementId); } }}><title>{`${title}：${scale.label} ${value.text}，${status(d)}`}</title></circle>}
              <g role="button" tabIndex={0} aria-label={`${title}，${status(d)}${kind === "none" ? "" : `，${value.text}`}，查看证据`} aria-pressed={active} aria-controls={detailId} className="cursor-pointer" onClick={() => selectRequirement(d.requirementId)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectRequirement(d.requirementId); } }}>
                <title>{title}</title><rect x={label.x - 68} y={label.y - 22} width="136" height="48" rx="8" fill={active ? "#eef2ff" : "white"} stroke={active ? "#c7d2fe" : "#e2e8f0"} />
                <text x={label.x} y={label.y - 3} textAnchor="middle" fontSize="16" fill={active ? "#4338ca" : "#334155"}>{dimensions.length > 6 ? `要求 ${i + 1}` : short}</text>
                <text x={label.x} y={label.y + 14} textAnchor="middle" fontSize="14" fill="#64748b">{kind === "none" ? status(d) : `${value.text} · ${status(d)}`}</text>
              </g>
            </g>;
          })}
        </svg> : <p className="py-6 text-sm text-slate-500">要求少于3项或超过8项时，请使用逐项证据对照，避免轴标签拥挤。</p>;

  if (mode === "overview") return <section className="skill-radar-overview min-w-0" aria-label="技能雷达概览图">{chart}</section>;

  return <section className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6" aria-label="证据联动雷达">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <h3 className="text-lg font-semibold">逐项核对</h3>
      <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-600">{dimensions.length} 项岗位要求</span>
    </div>
    <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-600" aria-label="雷达图例">
      <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-indigo-600" />{RADAR_STATUS.supported} / {RADAR_STATUS.partial}</span>
      <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-full border-2 border-amber-600 bg-white" />{RADAR_STATUS.claimed_only}</span>
      <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-full border border-dashed border-slate-400" />{RADAR_STATUS.gap}（不绘点）</span>
      <span>— {RADAR_STATUS.unsupported}</span>
    </div>
    <p className="mt-3 text-sm font-medium text-slate-700">{scale.label}</p>
    <details className="text-sm leading-6 text-slate-600"><summary className="w-fit cursor-pointer py-2 text-indigo-700">计量详情</summary><p>{supportScaleNote(scale)}</p></details>
    {scale.mode === "raw" && <p role="status" className="text-sm text-amber-900">{scale.reason}</p>}
        <div className="flex flex-wrap gap-2" aria-label="选择岗位要求">{dimensions.map((d, index) => <button key={d.requirementId} type="button" aria-pressed={dimension.requirementId === d.requirementId} aria-controls={detailId} className={`min-h-11 max-w-full break-words rounded-lg border px-3 py-2 text-left text-xs transition-colors ${dimension.requirementId === d.requirementId ? "border-indigo-300 bg-indigo-600 font-medium text-white shadow-sm" : "border-slate-200 bg-white text-slate-600 hover:border-indigo-200 hover:bg-indigo-50"}`} onClick={() => selectRequirement(d.requirementId)}><span className="mr-2 opacity-70">{String(index + 1).padStart(2, "0")}</span>{d.skill || d.title}</button>)}</div>
    <div className="mt-4 grid items-start gap-5 xl:grid-cols-[minmax(460px,0.95fr)_minmax(0,1.05fr)]">
      <div className="min-w-0 rounded-xl border border-slate-100 bg-slate-50/60 p-3 sm:p-4">

        {chart}
      </div>
      <div id={detailId} data-radar-detail className="order-first min-w-0 rounded-xl border border-indigo-100 bg-white p-3 sm:p-5 xl:order-last" aria-live="polite">
        <p className="text-sm text-slate-600">第 {selectedIndex + 1} 项 / {dimensions.length} 项</p>
        <h4 className="mt-2 break-words text-lg font-semibold leading-7">{dimension.title || dimension.skill}</h4>
        <p className="mt-3 text-base font-semibold text-indigo-900">{status(dimension)}</p>
        {measure.ratio != null && <p className="mt-2 text-base">{scale.label} {measure.text}</p>}
        {measure.issue && dimension.verdict !== "unsupported" && <p role="status" className="mt-2 text-sm text-amber-900">{measure.issue}；原始值 {String(measure.raw ?? "未记录")}。</p>}
        <details className="mt-2 text-sm text-slate-600"><summary className="cursor-pointer">原报告计量与等级</summary><SupportMeasureDetails raw={dimension.score} formulaVersion={dimension.formulaVersion} scale={scale}/><p>岗位权重 {dimension.weight}</p>{dimension.evidenceLevel!=null&&<p>实践证据 {evidenceLevelName(dimension.evidenceLevel)}，不等于能力认证。</p>}</details>
        {aiFallbackUsed && <p className="mt-3 text-sm text-amber-900">本报告为规则分析，此处显示规则解释。</p>}
        {item && item.aiStatus && !["validated", "not_used", "not_requested", "rules_only", "skipped"].includes(item.aiStatus) && <p className="mt-3 text-sm text-amber-900">本项 AI 解释未被采用，请按规则和来源核对。</p>}
        {item&&invalidNarrativeCitations(item).length>0&&<p className="mt-3 text-sm text-amber-900">历史AI解释含未对齐引用，请按规则与固定来源核对。</p>}
        {item ? <>
          <p className="mt-4 break-words text-base leading-7 text-slate-700">{(useAi&&item.aiExplanation ? readableCitationText(item,item.aiExplanation) : null) || item.explanation || "原报告未提供这项判断的说明。"}</p>
          {useAi&&item.aiExplanation&&<details className="mt-2 text-sm text-slate-600"><summary className="cursor-pointer">AI解释原文</summary><p className="mt-2 whitespace-pre-wrap leading-7">{item.aiExplanation}</p></details>}
          <details key={dimension.requirementId} open={evidenceExpanded} onToggle={event=>onEvidenceExpandedChange?.(event.currentTarget.open)} className="mt-4 rounded-lg border border-slate-200 bg-white p-3">
            <summary className="cursor-pointer text-sm text-indigo-700">查看本次授权引用片段（{item.evidenceList.length}）</summary>
            {item.evidenceList.length ? item.evidenceList.map((e, index) => <div key={`${e.citationId}:${index}`} className="mt-3 border-t border-slate-100 pt-3 text-xs">
              <p className="leading-6 text-sm"><SourceIdentity source={e} materials={materials} compact/> · 第{e.lineStart}—{e.lineEnd}行</p>
              {e.provenance === "reference" && <p className="mt-1 text-amber-800">参考材料，不能证明本人贡献。</p>}
              <EvidenceSnippet evidence={e} materials={materials} showContextNote={false}/><SourceIdentityDetails source={e} />
              {!e.contextComplete && <p className="mt-2 leading-5 text-amber-800">{e.contextNote || "引用上下文不完整，需要结合原报告核对。"}</p>}
            </div>) : <p className="mt-3 text-xs leading-5 text-slate-500">本项没有可定位的引用片段，可在完整报告中核对材料缺口。</p>}
          </details>
          {(useAi ? item.aiInformationGap || item.evidenceLevelGap : item.evidenceLevelGap) && <p className="mt-3 break-words text-sm leading-6 text-amber-800">待核对：{useAi ? item.aiInformationGap || item.evidenceLevelGap : item.evidenceLevelGap}</p>}

        </> : <p className="mt-4 text-sm leading-6 text-slate-600">{synthetic ? "这是预设的合成状态示例，没有真实来源文件。" : "本项没有提供可定位的报告引用。"} {dimension.verdict === "gap" ? "缺材料不代表没有能力。" : "材料支持程度不代表能力或录用结论。"}</p>}
      </div>
    </div>
  </section>;
}






