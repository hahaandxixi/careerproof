"use client";

import { displayMaterialTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import { useState } from "react";
import type { MatchReport, ReportComparison } from "@/lib/api/domain";
import { comparisonCounts, comparisonRows, comparisonSourceKey, filterComparisonRows, groupComparisonSources, sourceRecordKind, type ComparisonFilter, type ComparisonRow } from "@/lib/report-comparison-display";
import { compactSourceLabel, materialPathReadingText, sourceLocationId } from "@/lib/source-label";
import { aiStatusLabel } from "@/lib/report-display";
import { evidenceLevelName } from "@/lib/evidence-display";
import { GROWTH_CHANGES } from "@/lib/growth-workflow";
import ReportItemExplanation from "./ReportItemExplanation";
import { reportVersionHref } from "@/lib/report-navigation";

const BASIS_CHANGES = new Set(["job", "requirements", "rule_version", "retrieval_version", "model_or_mode"]);

const FILTERS: [ComparisonFilter, string][] = [["changed", "有变化"], ["all", "全部要求"], ["evidence", "证据有变化"], ["status", "判断状态有变化"], ["needs", "仍需补证"], ["unchanged", "没有变化"]];

function SourceGroup({ label, groups, reportId, requirementId, materials, sources, origin }: {
  label: string; groups: ComparisonRow["added"]; reportId: string; requirementId: string; materials: MatchReport["materials"]; sources?: ComparisonRow["old"]; origin?: string;
}) {
  return <section className="min-w-0" aria-label={label}>
    <ul className="min-w-0 divide-y divide-slate-100">{groups.map((group, index) => {
      const source = group.source, short = compactSourceLabel(source, materials);
      const sourceIndex = sources?.evidenceList.findIndex(entry => comparisonSourceKey(entry) === comparisonSourceKey(source)) ?? -1;
      const anchor = group.citationIds[0] ? `citation-${group.citationIds[0]}`
        : sourceIndex >= 0 ? sourceLocationId(requirementId, source, sourceIndex) : `requirement-${requirementId}`;
      return <li key={index} className="min-w-0 space-y-1 py-3">
        <Link className="break-words font-medium text-[#1d4a40] underline" href={reportVersionHref(reportId, origin, `#${anchor}`)} target="_blank" rel="noopener" title="在新标签页打开原报告">{short.fileName} · {source.lineStart > 0 ? `第 ${source.lineStart}–${source.lineEnd} 行` : "行号未记录"}</Link>
        <p className="break-words text-sm leading-6 text-slate-600">{short.material} · {sourceRecordKind(source)}</p>
        {index === 0 && source.snippet && <pre className="comparison-source-preview">{source.snippet}</pre>}
        {source.provenance === "reference" && <p className="text-xs text-slate-600">第三方参考，不作为个人实践证明。</p>}
        <details className="min-w-0 text-xs leading-6 text-slate-600"><summary className="w-fit cursor-pointer py-1">完整来源与源码</summary>
          <dl className="min-w-0 space-y-1 py-2 [overflow-wrap:anywhere]">
            <div><dt className="inline">原始路径：</dt><dd className="inline">{source.filePath}</dd></div>
            <div><dt className="inline">引用标识：</dt><dd className="inline">{group.citationIds.join("、") || "未记录模型引用标识"}</dd></div>
            <div><dt className="inline">材料版本 ID：</dt><dd className="inline">{source.projectVersionId || "未记录项目版本"}</dd></div>
            <div><dt className="inline">来源 ID：</dt><dd className="inline">{group.sourceIds.join("、") || "未记录"}</dd></div>
            <div><dt className="inline">文件 ID：</dt><dd className="inline">{source.projectFileId || "未记录"}</dd></div>
            <div><dt className="inline">内容摘要：</dt><dd className="inline">{source.contentHash || "未记录"}</dd></div>
          </dl>
          <p className="break-words">{source.contextComplete ? "保存的片段上下文完整" : "保存的片段上下文不完整，请到原报告核对"}{source.contextNote ? `：${source.contextNote}` : ""}</p>
          {source.snippet ? <pre className="mt-2 max-h-64 max-w-full overflow-auto rounded-lg bg-slate-50 p-3 text-xs leading-6">{source.snippet}</pre> : <p>未保存源码片段，请打开原报告核对。</p>}
        </details>
      </li>;
    })}</ul>
  </section>;
}

const CHANGE_LABELS: Record<string, string> = {
  requirement: "要求变化", item_added: "新增要求", item_removed: "移除要求",
  rule_version: "规则变化", review: "复核变化", ai_status: "AI 状态变化",
  level: "等级变化", interpretation: "说明变化", advice: "建议变化",
};

function rowChanges(row: ComparisonRow) {
  const labels = [
    ...(row.statusChanged ? ["判断变化"] : []),
    ...(row.evidenceChanged ? ["引用变化"] : []),
    ...row.item.changes.filter(key => key !== "evidence").map(key => CHANGE_LABELS[key] ?? GROWTH_CHANGES[key] ?? "其他变化"),
    ...(row.levelChanged ? ["等级变化"] : []),
  ];
  if (row.item.status !== "existing") labels.push(row.item.status === "added" ? "新增要求" : "移除要求");
  return [...new Set(labels.length ? labels : [row.changed ? "其他变化" : "无变化"])];
}

function StatusFlow({ row }: { row: ComparisonRow }) {
  return <span className="comparison-status-flow">
    <span className="comparison-state" data-verdict={row.old?.verdict ?? "absent"}>{row.baseStatus}</span>
    <span aria-hidden="true">→</span>
    <span className="comparison-state" data-verdict={row.now?.verdict ?? "absent"}>{row.targetStatus}</span>
  </span>;
}

function CitationChanges({ row, value, origin }: { row: ComparisonRow; value: ReportComparison; origin?: string }) {
  const groups = [
    { key: "added", label: "新增", items: row.added, reportId: value.targetId, materials: value.targetMaterials, sources: row.now, side: "B 对照报告" },
    { key: "removed", label: "未再引用", items: row.removed, reportId: value.baseId, materials: value.baseMaterials, sources: row.old, side: "A 基准报告" },
    { key: "retained", label: "沿用", items: row.retained, reportId: value.targetId, materials: value.targetMaterials, sources: row.now, side: "B 对照报告" },
  ] as const;
  const max = Math.max(...groups.map(group => group.items.length));
  const [active, setActive] = useState(groups.find(group => group.items.length)?.key);
  if (max === 0) {
    const a = groupComparisonSources(row.old?.evidenceList ?? []).length;
    const b = groupComparisonSources(row.now?.evidenceList ?? []).length;
    return <p className="text-sm text-slate-600">引用：A {a} 处 → B {b} 处</p>;
  }
  const selected = groups.find(group => group.key === active);
  return <div className="space-y-2">
    <div className="comparison-source-chart" role="group" aria-label="引用数量变化">
      {groups.map(group => <button key={group.key} type="button" data-kind={group.key} aria-pressed={active === group.key} disabled={!group.items.length}
        aria-controls="comparison-current-sources" onClick={() => setActive(group.key)}>
        <span>{group.label}</span><span className="comparison-source-track" aria-hidden="true">{!!group.items.length && <i style={{width:`${group.items.length / max * 100}%`}} />}</span>
        <span>{group.items.length} 处</span>
      </button>)}
    </div>
    {selected && <div id="comparison-current-sources" className="border-t border-slate-200 pt-2">
      <p className="text-sm text-slate-600">{selected.side}</p>
      <SourceGroup label={selected.label} groups={selected.items} reportId={selected.reportId} requirementId={row.item.requirementId}
        materials={selected.materials} sources={selected.sources} origin={origin} />
    </div>}
  </div>;
}

function RequirementChange({ row, value, origin }: { row: ComparisonRow; value: ReportComparison; origin?: string }) {
  const { item } = row;
  const gap = materialPathReadingText(item.targetInformationGap || "", [...value.baseMaterials, ...value.targetMaterials]);
  return <div className="min-w-0 space-y-3">
    <h3 className="break-words font-semibold text-slate-900">{item.title}</h3>
    <StatusFlow row={row} />
    <CitationChanges row={row} value={value} origin={origin} />
    {gap && <p className="text-sm leading-6 text-slate-700">待核对：{/规则层保存了未发送证据/.test(gap) ? "旧报告未保存具体缺口，请查看原报告。" : gap}</p>}
    <details className="min-w-0 border-t border-slate-100 pt-2"><summary className="w-fit cursor-pointer py-1 text-[#1d4a40]">判断依据、建议与复核</summary>
      <div className="min-w-0 space-y-3 pt-2 [overflow-wrap:anywhere]">
        {item.changes.includes("rule_version") && <dl className="space-y-1 text-sm">
          <div><dt className="inline">判断公式：</dt><dd className="inline">A {row.old?.formulaVersion || "未记录"} → B {row.now?.formulaVersion || "未记录"}</dd></div>
          <div><dt className="inline">证据等级规则：</dt><dd className="inline">A {row.old?.evidenceLevelVersion || "未记录"} → B {row.now?.evidenceLevelVersion || "未记录"}</dd></div>
        </dl>}
        {row.levelChanged && <p>实践证据等级：{item.baseLevel == null ? "未评级" : evidenceLevelName(item.baseLevel)} → {item.targetLevel == null ? "未评级" : evidenceLevelName(item.targetLevel)}</p>}
        {item.changes.includes("requirement") && <p>岗位要求或权重有变化，请结合原报告核对。</p>}
        <p className="text-sm leading-6 text-slate-600">权重 {item.targetRequirement?.weight ?? item.baseRequirement?.weight ?? "未记录"} · AI 状态 {aiStatusLabel(item.baseAiStatus)} → {aiStatusLabel(item.targetAiStatus)} · 本人复核 {item.baseReview ?? "未记录"} → {item.targetReview ?? "未记录"}</p>
        {gap !== (item.targetInformationGap || "") && <p>{item.targetInformationGap}</p>}
        <ReportItemExplanation item={item} targetLabel="当前报告" />
      </div>
    </details>
  </div>;
}

export default function ReportComparisonView({ value, base, current, origin }: { value: ReportComparison; base: MatchReport; current: MatchReport; origin?: string }) {
  const [filter, setFilter] = useState<ComparisonFilter>("changed");
  const rows = comparisonRows(value, base, current), counts = comparisonCounts(rows);
  const visible = filterComparisonRows(rows, filter);
  const [selectedId, setSelectedId] = useState("");
  const selected = visible.find(row => row.item.requirementId === selectedId) ?? visible[0];
  const basisChanges = value.contextChanges.filter(key => BASIS_CHANGES.has(key));
  return <div className="min-w-0 space-y-4 text-base" aria-label="按岗位要求查看证据变化">
    {!!basisChanges.length && <p role="note" className="rounded-md bg-amber-50 p-3 text-sm text-amber-950">比较依据变化：{basisChanges.map(key => GROWTH_CHANGES[key] ?? key).join("、")}。</p>}
    <div className="comparison-filter-bar" role="group" aria-label="筛选要求变化">{FILTERS.map(([key, label]) => <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)} className="comparison-filter">{label}<span className="comparison-filter-count">{counts[key]}</span></button>)}</div>
    {counts.changed === 0 && <p className="comparison-no-change">本次没有检测到变化。可切换“全部要求”或“没有变化”查看原记录。</p>}
    {visible.length === 0 && counts.changed > 0 && <p className="py-3 text-slate-600">没有符合此筛选的要求。</p>}
    {!!visible.length && <div className="report-comparison-workbench">
      <div className="min-w-0">
        <table className="report-comparison-matrix w-full text-left text-sm">
          <thead><tr><th scope="col">岗位要求</th><th scope="col">A 基准 → B 对照</th><th scope="col">变化</th></tr></thead>
          <tbody>{visible.map(row => <tr key={row.item.requirementId} data-selected={selected === row}>
            <th scope="row"><button type="button" className="w-full text-left" aria-pressed={selected === row} aria-controls="comparison-requirement-reader" onClick={() => setSelectedId(row.item.requirementId)}>
              <span className="block font-semibold" title={row.item.title}>{row.now?.skill || row.old?.skill || row.item.title}</span>
            </button></th>
            <td><StatusFlow row={row} /></td><td><span className="comparison-change-tags">{rowChanges(row).map(label => <span key={label}>{label}</span>)}</span></td>
          </tr>)}</tbody>
        </table>
      </div>
      {selected && <article id="comparison-requirement-reader" className="report-comparison-reader min-w-0" key={selected.item.requirementId}><RequirementChange row={selected} value={value} origin={origin} /></article>}
    </div>}
    <details className="min-w-0 border-t border-slate-200 pt-3"><summary className="w-fit cursor-pointer py-1 text-[#1d4a40]">两次报告、材料版本与比较范围</summary>
      <div className="space-y-3 pt-3 leading-6 [overflow-wrap:anywhere]">
        {!!value.contextChanges.length && <p>变化背景：{value.contextChanges.map(key => GROWTH_CHANGES[key] ?? key).join("、")}</p>}
        {[{label: "基准材料", rows: value.baseMaterials}, {label: "当前材料", rows: value.targetMaterials}].map(side => <div key={side.label}><h3 className="font-medium">{side.label}</h3><ul>{side.rows.map(m => <li key={`${m.kind}-${m.id}`}>{displayMaterialTitle(m.title, m.id)} · 第 {m.versionNumber} 版<details className="text-xs text-slate-600"><summary className="w-fit cursor-pointer">版本校验信息</summary><p>{m.id} · {m.contentHash}</p></details></li>)}</ul></div>)}
        <p>上传的测试记录须结合对应源码版本核对，平台未独立运行测试。</p>
        <ul className="space-y-1 text-xs text-slate-600">{value.limitations.map(note => <li key={note}>{note}</li>)}</ul>
      </div>
    </details>
  </div>;
}
