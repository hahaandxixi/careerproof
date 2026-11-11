"use client";

import { displayMaterialTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import { useState } from "react";
import type { MatchReport, ReportComparison } from "@/lib/api/domain";
import { comparisonCounts, comparisonRows, comparisonSourceKey, filterComparisonRows, sourceRecordKind, type ComparisonFilter, type ComparisonRow } from "@/lib/report-comparison-display";
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
  // Zero-count groups stay as flat statements, never as an openable empty disclosure.
  if (!groups.length) return <p className="border-t border-slate-100 py-2 text-sm leading-6 text-slate-500">{label} · 0 处，没有可展开的记录。</p>;
  return <details open={label === "新增引用"} className="min-w-0 border-t border-slate-100 py-2">
    <summary className="w-fit cursor-pointer py-1 text-[#1d4a40]">{label} · {groups.length} 处</summary>
    <ul className="min-w-0 divide-y divide-slate-100">{groups.map((group, index) => {
      const source = group.source, short = compactSourceLabel(source, materials);
      const sourceIndex = sources?.evidenceList.findIndex(entry => comparisonSourceKey(entry) === comparisonSourceKey(source)) ?? -1;
      const anchor = group.citationIds[0] ? `citation-${group.citationIds[0]}`
        : sourceIndex >= 0 ? sourceLocationId(requirementId, source, sourceIndex) : `requirement-${requirementId}`;
      return <li key={index} className="min-w-0 space-y-1 py-3">
        <Link className="break-words font-medium text-[#1d4a40] underline" href={reportVersionHref(reportId, origin, `#${anchor}`)}>{short.fileName} · {source.lineStart > 0 ? `第 ${source.lineStart}–${source.lineEnd} 行` : "行号未记录"}</Link>
        <p className="break-words text-sm leading-6 text-slate-600">{short.material} · {sourceRecordKind(source)}</p>
        {label === "新增引用" && source.snippet && <pre className="comparison-source-preview">{source.snippet}</pre>}
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
  </details>;
}

function RequirementChange({ row, value, origin }: { row: ComparisonRow; value: ReportComparison; origin?: string }) {
  const { item } = row;
  const gap = materialPathReadingText(item.targetInformationGap || "", [...value.baseMaterials, ...value.targetMaterials]);
  const tests = row.added.filter(group => sourceRecordKind(group.source) === "测试代码引用").length;
  const records = row.added.filter(group => sourceRecordKind(group.source) === "记录文件引用（需核对原文）").length;
  return <div className="min-w-0 space-y-3">
    <div className="flex flex-wrap items-start justify-between gap-2"><h3 className="min-w-0 flex-1 break-words font-semibold text-slate-900">{item.title}</h3><span className="shrink-0 text-xs leading-6 text-slate-600">权重 {item.targetRequirement?.weight ?? item.baseRequirement?.weight ?? "未记录"}</span></div>
    <p className="flex flex-wrap items-center gap-2 text-sm"><span className="text-slate-600">基准 → 当前</span><span>{row.baseStatus}</span><span aria-hidden="true">→</span><span className={row.statusChanged ? "font-medium text-[#1d4a40]" : "text-slate-700"}>{row.targetStatus}</span></p>
    <p className="text-base leading-7 text-slate-700">{row.evidenceChanged && item.status==="existing" ? row.statusChanged ? "判断状态已改变，请核对相关来源。" : "引用范围有变化，判断状态未改变。" : row.summary}</p>
    {(row.added.length > 0 || row.removed.length > 0 || row.retained.length > 0) && <div className="space-y-3">
      {!!row.removed.length && <section aria-label="A 基准报告引用"><h4 className="font-medium">A 基准报告</h4>
        <SourceGroup label="移除展示的引用" groups={row.removed} reportId={value.baseId} requirementId={item.requirementId} materials={value.baseMaterials} sources={row.old} origin={origin} />
      </section>}
      {(row.added.length > 0 || row.retained.length > 0) && <section aria-label="B 对照报告引用"><h4 className="font-medium">B 对照报告</h4>
        {!!row.added.length && <SourceGroup label="新增引用" groups={row.added} reportId={value.targetId} requirementId={item.requirementId} materials={value.targetMaterials} sources={row.now} origin={origin} />}
        {!!row.retained.length && <SourceGroup label="保留展示的引用（当前版本）" groups={row.retained} reportId={value.targetId} requirementId={item.requirementId} materials={value.targetMaterials} sources={row.now} origin={origin} />}
      </section>}
    </div>}
    {row.added.length === 0 && row.removed.length === 0 && row.retained.length === 0 && <p className="text-sm leading-6 text-slate-600">本项没有新增、移除或保留的可展示引用；判断或文本变化见上。</p>}
    {item.targetInformationGap&&<p className="text-base leading-7 text-slate-700">仍待核对：{/规则层保存了未发送证据/.test(item.targetInformationGap)?"旧记录只保存了分析范围提示，具体缺口原文无法恢复，请到原报告核对。":gap}</p>}
    {gap !== (item.targetInformationGap || "") && <details className="text-sm text-slate-600"><summary className="disclosure">保存原文与完整材料定位</summary><p className="break-words leading-7">{item.targetInformationGap}</p></details>}
    {row.levelChanged && <p className="text-xs leading-6 text-slate-600">实践证据等级：{item.baseLevel == null ? "未评级" : evidenceLevelName(item.baseLevel)} → {item.targetLevel == null ? "未评级" : evidenceLevelName(item.targetLevel)}。等级与引用变化同时展示，不推断因果。</p>}
    {(tests > 0 || records > 0) && <p className="text-sm leading-6 text-slate-600">新增测试代码引用 {tests} 处、记录文件引用 {records} 处。运行结果需核对原文与源码版本。</p>}
    <details className="min-w-0 border-t border-slate-100 py-2"><summary className="w-fit cursor-pointer py-1 text-[#1d4a40]">判断依据、建议与复核记录</summary>
      <div className="min-w-0 space-y-3 pt-3 [overflow-wrap:anywhere]">
        {item.changes.includes("rule_version") && <dl className="space-y-1 text-sm">
          <div><dt className="inline">判断公式：</dt><dd className="inline">A {row.old?.formulaVersion || "未记录"} → B {row.now?.formulaVersion || "未记录"}</dd></div>
          <div><dt className="inline">证据等级规则：</dt><dd className="inline">A {row.old?.evidenceLevelVersion || "未记录"} → B {row.now?.evidenceLevelVersion || "未记录"}</dd></div>
        </dl>}
        {item.changes.includes("requirement") && <p>岗位要求或权重有变化，请结合两份原报告核对比较范围。</p>}
        <p className="text-xs leading-6 text-slate-600">AI 状态：{aiStatusLabel(item.baseAiStatus)} → {aiStatusLabel(item.targetAiStatus)}；本人复核：{item.baseReview ?? "未记录"} → {item.targetReview ?? "未记录"}。复核状态是当前读取值。</p>
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
    {!!basisChanges.length && <p role="note" className="rounded-md bg-amber-50 p-3 text-sm text-amber-950">比较依据有变化：{basisChanges.map(key => GROWTH_CHANGES[key] ?? key).join("、")}。请核对两份报告各自的判断口径。</p>}
    <div className="comparison-filter-bar" role="group" aria-label="筛选要求变化">{FILTERS.map(([key, label]) => <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)} className="comparison-filter">{label}<span className="comparison-filter-count">{counts[key]}</span></button>)}</div>
    {counts.changed === 0 && <p className="comparison-no-change">本次没有检测到变化。可切换“全部要求”或“没有变化”查看原记录。</p>}
    {visible.length === 0 && counts.changed > 0 && <p className="py-3 text-slate-600">没有符合此筛选的要求。</p>}
    {!!visible.length && <div className="report-comparison-workbench">
      <div className="min-w-0">
        <table className="report-comparison-matrix w-full text-left text-sm">
          <thead><tr><th scope="col">岗位要求</th><th scope="col">A 基准</th><th scope="col">B 对照</th></tr></thead>
          <tbody>{visible.map(row => <tr key={row.item.requirementId} data-selected={selected === row}>
            <th scope="row"><button type="button" className="w-full text-left" aria-pressed={selected === row} aria-controls="comparison-requirement-reader" onClick={() => setSelectedId(row.item.requirementId)}>
              <span className="block font-semibold">{row.item.title}</span>
              <span className="block text-xs font-normal">{[row.statusChanged && "判断变化", row.evidenceChanged && "引用变化"].filter(Boolean).join(" · ") || (row.changed ? "其他变化" : "无变化")}</span>
            </button></th>
            <td>{row.baseStatus}</td><td>{row.targetStatus}</td>
          </tr>)}</tbody>
        </table>
      </div>
      {selected && <article id="comparison-requirement-reader" className="report-comparison-reader min-w-0" key={selected.item.requirementId}><RequirementChange row={selected} value={value} origin={origin} /></article>}
    </div>}
    <details className="min-w-0 border-t border-slate-200 pt-3"><summary className="w-fit cursor-pointer py-1 text-[#1d4a40]">两次报告、材料版本与比较范围</summary>
      <div className="space-y-3 pt-3 leading-6 [overflow-wrap:anywhere]">
        <p>变化背景：{value.contextChanges.map(key => GROWTH_CHANGES[key] ?? key).join("、") || "未记录背景变化"}。材料版本变化与各项判断、引用变化分别记录。</p>
        {[{label: "基准材料", rows: value.baseMaterials}, {label: "当前材料", rows: value.targetMaterials}].map(side => <div key={side.label}><h3 className="font-medium">{side.label}</h3><ul>{side.rows.map(m => <li key={`${m.kind}-${m.id}`}>{displayMaterialTitle(m.title, m.id)} · 第 {m.versionNumber} 版<details className="text-xs text-slate-600"><summary className="w-fit cursor-pointer">版本校验信息</summary><p>{m.id} · {m.contentHash}</p></details></li>)}</ul></div>)}
        <p>测试代码引用与运行记录引用分别展示。上传的测试输出仍需核对内容及源码版本，不是平台独立执行结果；未再展示的引用仍可在基准报告中查看。</p>
        <ul className="space-y-1 text-xs text-slate-600">{value.limitations.map(note => <li key={note}>{note}</li>)}</ul>
      </div>
    </details>
  </div>;
}
