"use client";
import { useId, useState } from "react";
import type { ApplicationView } from "@/lib/api/client";
import type { ReportItem } from "@/lib/api/domain";
import { RADAR_STATUS, radarPointKind, radarScore, radarSegments, radarSelection } from "@/lib/skill-radar";

export default function SkillRadar({ dimensions, items = [], initialRequirementId = "", synthetic = false }: {
  dimensions: ApplicationView["dimensions"]; items?: ReportItem[]; initialRequirementId?: string; synthetic?: boolean;
}) {
  const [selectedId, setSelectedId] = useState(initialRequirementId);
  const detailId = useId();
  const { dimension, item } = radarSelection(dimensions, selectedId, items);
  if (!dimension) return null;
  const selectedIndex = dimensions.indexOf(dimension);
  const point = (index: number, ratio: number) => {
    const angle = index * 2 * Math.PI / dimensions.length - 3 * Math.PI / 4;
    return { x: 200 + 108 * ratio * Math.cos(angle), y: 200 + 108 * ratio * Math.sin(angle) };
  };
  const score = radarScore(dimension);
  const status = (d: typeof dimension) => RADAR_STATUS[d.verdict] ?? "暂不可评";
  return <section className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5" aria-label="证据联动雷达">
    <h3 className="font-semibold">岗位要求雷达 · 证据联动</h3>
    <p className="mt-2 text-xs leading-5 text-slate-500">点选要求，核对原报告判断与来源。实心点有证据，空心点仅自述；缺材料不绘点，不可评用“—”。分数沿用原报告，不填充面积。</p>
    <div className="mt-3 grid items-start gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        {dimensions.length >= 3 && dimensions.length <= 8 ? <svg className="mx-auto w-full max-w-[440px]" viewBox="0 0 400 400" role="group" aria-label="岗位要求分数，点选轴标签或下方要求按钮查看证据">
          <circle cx="200" cy="200" r="108" fill="#f8fafc" />
          {[25, 50, 75, 100].map(value => <g key={value}><circle cx="200" cy="200" r={108 * value / 100} fill="none" stroke="#e2e8f0" /><text x="204" y={200 - 108 * value / 100 - 4} fill="#94a3b8" fontSize="10">{value}</text></g>)}
          <text x="204" y="212" fill="#94a3b8" fontSize="10">0</text>
          {radarSegments(dimensions).map(([a, b]) => {
            const start = point(a, radarScore(dimensions[a])! / 100), end = point(b, radarScore(dimensions[b])! / 100);
            return <line key={a} x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="#a5b4fc" strokeWidth="2" />;
          })}
          {dimensions.map((d, i) => {
            const end = point(i, 1), rawLabel = point(i, 1.6), label = {x:Math.max(61,Math.min(339,rawLabel.x)),y:Math.max(30,Math.min(370,rawLabel.y))}, dot = point(i, (radarScore(d) ?? 0) / 100);
            const kind = radarPointKind(d), active = i === selectedIndex;
            const title = d.skill || d.title;
            const short = Array.from(title).length > 10 ? Array.from(title).slice(0, 9).join("") + "…" : title;
            return <g key={d.requirementId}>
              <line x1="200" y1="200" x2={end.x} y2={end.y} stroke={active ? "#818cf8" : "#cbd5e1"} strokeWidth={active ? 2 : 1} />
              {kind !== "none" && <circle cx={dot.x} cy={dot.y} r={active ? 7 : 5} fill={kind === "claimed" ? "white" : d.verdict === "partial" ? "#c7d2fe" : "#4f46e5"} stroke={kind === "claimed" ? "#d97706" : "#4f46e5"} strokeWidth="2"><title>{`${title}：${radarScore(d)}，${status(d)}`}</title></circle>}
              <g role="button" tabIndex={0} aria-label={`${title}，${status(d)}，${radarScore(d) ?? "不可评"}，查看证据`} aria-pressed={active} aria-controls={detailId} className="cursor-pointer" onClick={() => setSelectedId(d.requirementId)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedId(d.requirementId); } }}>
                <rect x={label.x - 58} y={label.y - 20} width="116" height="44" rx="8" fill={active ? "#eef2ff" : "white"} />
                <text x={label.x} y={label.y - 3} textAnchor="middle" fontSize="12" fill={active ? "#4338ca" : "#334155"}>{dimensions.length > 6 ? `要求 ${i + 1}` : short}</text>
                <text x={label.x} y={label.y + 14} textAnchor="middle" fontSize="10" fill="#64748b">{radarScore(d) ?? "—"} · {status(d)}</text>
              </g>
            </g>;
          })}
        </svg> : <p className="py-6 text-sm text-slate-500">要求少于3项或超过8项时，使用下方逐项证据对照，避免轴标签拥挤。</p>}
        <div className="flex flex-wrap gap-2" aria-label="选择岗位要求">{dimensions.map(d => <button key={d.requirementId} type="button" aria-pressed={dimension.requirementId === d.requirementId} aria-controls={detailId} className={`min-h-11 max-w-full break-words rounded-lg border px-3 py-2 text-left text-xs ${dimension.requirementId === d.requirementId ? "border-indigo-300 bg-indigo-50 text-indigo-800" : "border-slate-200 text-slate-600"}`} onClick={() => setSelectedId(d.requirementId)}>{d.skill || d.title}</button>)}</div>
      </div>
      <div id={detailId} className="min-w-0 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4" aria-live="polite">
        <p className="text-xs text-indigo-600">第 {selectedIndex + 1} 项 · 权重 {dimension.weight}</p>
        <h4 className="mt-2 break-words font-semibold">{dimension.title || dimension.skill}</h4>
        <div className="mt-3 flex flex-wrap items-end gap-3"><p className="text-3xl font-semibold text-indigo-700">{score ?? "—"}{score !== null && <span className="ml-1 text-xs font-normal text-slate-500">/ 100</span>}</p><p className="pb-1 text-sm text-slate-600">{status(dimension)}</p></div>
        {dimension.evidenceLevel != null && <p className="mt-2 text-xs text-slate-500">实践证据 {dimension.evidenceLevel}/5 · {dimension.evidenceLevelSource === "ai_preliminary" ? "AI初评，待独立核验" : "原报告结果"}</p>}
        {item ? <>
          <p className="mt-4 break-words text-sm leading-6 text-slate-700">{item.aiExplanation || item.explanation || "原报告未提供这项判断的说明。"}</p>
          {item.aiInformationGap && <p className="mt-3 break-words text-xs leading-5 text-amber-800">待核对：{item.aiInformationGap}</p>}
          <details key={dimension.requirementId} className="mt-4 rounded-lg border border-slate-200 bg-white p-3">
            <summary className="cursor-pointer text-sm text-indigo-700">查看本次授权引用片段（{item.evidenceList.length}）</summary>
            {item.evidenceList.length ? item.evidenceList.map((e, index) => <div key={`${e.citationId}:${index}`} className="mt-3 border-t border-slate-100 pt-3 text-xs">
              <p className="break-all leading-5">{e.citationId || "原报告引用"} · {e.filePath} · 第{e.lineStart}—{e.lineEnd}行</p>
              {e.provenance === "reference" && <p className="mt-1 text-amber-800">参考材料，不能证明本人贡献。</p>}
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2">{e.snippet}</pre>
              {!e.contextComplete && <p className="mt-2 leading-5 text-amber-800">{e.contextNote || "引用上下文不完整，需要结合原报告核对。"}</p>}
            </div>) : <p className="mt-3 text-xs leading-5 text-slate-500">本项没有可定位的引用片段，可在完整报告中核对材料缺口。</p>}
          </details>
        </> : <p className="mt-4 text-sm leading-6 text-slate-600">{synthetic ? "这是预设的合成状态示例，没有真实来源文件。" : "本项没有提供可定位的报告引用。"} {dimension.verdict === "gap" ? "缺材料不代表没有能力。" : "材料支持程度不代表能力或录用结论。"}</p>}
      </div>
    </div>
  </section>;
}
