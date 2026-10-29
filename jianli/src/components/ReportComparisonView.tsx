"use client";

import Link from "next/link";
import { useState } from "react";
import type { MatchReport, ReportComparison } from "@/lib/api/domain";
import { comparisonCounts, comparisonRows, filterComparisonRows, sourceRecordKind, type ComparisonFilter, type ComparisonRow } from "@/lib/report-comparison-display";
import { compactSourceLabel } from "@/lib/source-label";
import { evidenceLevelName } from "@/lib/evidence-display";
import { GROWTH_CHANGES } from "@/lib/growth-workflow";
import ReportItemExplanation from "./ReportItemExplanation";

const FILTERS: [ComparisonFilter, string][] = [["changed", "有变化"], ["all", "全部要求"], ["evidence", "证据有变化"], ["status", "判断状态有变化"], ["needs", "仍需补证"], ["unchanged", "没有变化"]];

function SourceGroup({ label, groups, reportId, requirementId, materials }: {
  label: string; groups: ComparisonRow["added"]; reportId: string; requirementId: string; materials: MatchReport["materials"];
}) {
  return <details className="min-w-0 border-t border-slate-100 py-2">
    <summary className="w-fit cursor-pointer py-1 text-indigo-700">{label} · {groups.length} 处</summary>
    {!groups.length && <p className="py-2 text-slate-600">没有记录{label}。</p>}
    <ul className="min-w-0 divide-y divide-slate-100">{groups.map((group, index) => {
      const source = group.source, short = compactSourceLabel(source, materials);
      const anchor = group.citationIds[0] ? `citation-${group.citationIds[0]}` : `requirement-${requirementId}`;
      return <li key={index} className="min-w-0 space-y-1 py-3">
        <Link className="break-words font-medium text-indigo-700 underline" href={`/reports/${reportId}#${anchor}`}>{short.fileName} · {source.lineStart > 0 ? `第 ${source.lineStart}–${source.lineEnd} 行` : "行号未记录"}</Link>
        <p className="break-words text-xs leading-6 text-slate-600">{short.material} · {sourceRecordKind(source)}</p>
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

function RequirementChange({ row, value, showTitle = true }: { row: ComparisonRow; value: ReportComparison; showTitle?: boolean }) {
  const { item } = row;
  const tests = row.added.filter(group => sourceRecordKind(group.source) === "测试代码引用").length;
  const records = row.added.filter(group => sourceRecordKind(group.source) === "记录文件引用（需核对原文）").length;
  return <div className="min-w-0 space-y-3">
    <div className="flex flex-wrap items-start justify-between gap-2">{showTitle && <h3 className="min-w-0 flex-1 break-words font-semibold text-slate-900">{item.title}</h3>}<span className="shrink-0 text-xs leading-6 text-slate-600">权重 {item.targetRequirement?.weight ?? item.baseRequirement?.weight ?? "未记录"}</span></div>
    <p className="flex flex-wrap items-center gap-2 text-sm"><span className="text-slate-600">基准 → 当前</span><span>{row.baseStatus}</span><span aria-hidden="true">→</span><span className={row.statusChanged ? "font-medium text-indigo-700" : "text-slate-700"}>{row.targetStatus}</span></p>
    <p className="leading-6 text-slate-700">{row.summary}</p>
    {row.levelChanged && <p className="text-xs leading-6 text-slate-600">实践证据等级：{item.baseLevel == null ? "未评级" : evidenceLevelName(item.baseLevel)} → {item.targetLevel == null ? "未评级" : evidenceLevelName(item.targetLevel)}。等级与引用变化同时展示，不推断因果。</p>}
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600"><span>新增 {row.added.length}</span><span>移除展示 {row.removed.length}</span><span>保留展示 {row.retained.length}</span></div>
    {(tests > 0 || records > 0) && <p className="text-xs leading-6 text-slate-600">新增引用中：测试代码 {tests} 处、记录文件 {records} 处（按文件名区分）。是否执行成功，需核对记录原文及对应源码版本。</p>}
    <SourceGroup label="新增引用" groups={row.added} reportId={value.targetId} requirementId={item.requirementId} materials={value.targetMaterials} />
    <SourceGroup label="移除展示的引用" groups={row.removed} reportId={value.baseId} requirementId={item.requirementId} materials={value.baseMaterials} />
    <SourceGroup label="保留展示的引用（当前版本）" groups={row.retained} reportId={value.targetId} requirementId={item.requirementId} materials={value.targetMaterials} />
    <details className="min-w-0 border-t border-slate-100 py-2"><summary className="w-fit cursor-pointer py-1 text-indigo-700">判断依据、建议与复核记录</summary>
      <div className="min-w-0 space-y-3 pt-3 [overflow-wrap:anywhere]">
        {item.changes.includes("requirement") && <p>岗位要求或权重有变化，请结合两份原报告核对比较范围。</p>}
        <p className="text-xs leading-6 text-slate-600">AI 状态：{item.baseAiStatus ?? "未记录"} → {item.targetAiStatus ?? "未记录"}；本人复核：{item.baseReview ?? "未记录"} → {item.targetReview ?? "未记录"}。复核状态是当前读取值。</p>
        <ReportItemExplanation item={item} targetLabel="当前报告" />
      </div>
    </details>
  </div>;
}

export default function ReportComparisonView({ value, base, current }: { value: ReportComparison; base: MatchReport; current: MatchReport }) {
  const [filter, setFilter] = useState<ComparisonFilter>("changed");
  const rows = comparisonRows(value, base, current), counts = comparisonCounts(rows);
  const visible = filterComparisonRows(rows, filter);
  return <div className="min-w-0 space-y-4 text-sm" aria-label="按岗位要求查看证据变化">
    <dl className="grid grid-cols-1 gap-3 rounded-xl bg-slate-50 p-4 sm:grid-cols-3">
      {[["证据有变化", counts.evidence], ["判断状态有变化", counts.status], ["当前仍需补证", counts.needs]].map(([label, count]) => <div key={label}><dt className="text-xs text-slate-600">{label}</dt><dd className="mt-1 text-2xl font-semibold text-slate-900">{count}<span className="ml-1 text-sm font-normal">项</span></dd></div>)}
    </dl>
    <p className="text-xs leading-6 text-slate-600">判断状态统计原报告的支持状态；仍需补证包括部分支持、材料缺口及本人标记需修正的要求。引用变化不代表源码已修改、测试已通过或能力提升。</p>
    <div className="flex flex-wrap gap-2" role="group" aria-label="筛选要求变化">{FILTERS.map(([key, label]) => <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)} className={`min-h-10 rounded-full px-3 py-2 text-sm ${filter === key ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`}>{label} {counts[key]}</button>)}</div>
    <p role="status" className="text-xs text-slate-600">显示 {visible.length} / {counts.all} 项要求</p>
    {counts.changed === 0 && <p className="rounded-lg bg-slate-50 p-3">本次没有检测到变化。可切换“全部要求”或“没有变化”查看原记录。</p>}
    {visible.length === 0 && counts.changed > 0 && <p className="py-3 text-slate-600">没有符合此筛选的要求。</p>}
    <div className="min-w-0 space-y-3">{visible.map(row => row.changed
      ? <article key={row.item.requirementId} className="min-w-0 rounded-xl border border-slate-200 p-4"><RequirementChange row={row} value={value} /></article>
      : <details key={row.item.requirementId} className="min-w-0 rounded-xl border border-slate-200 p-4"><summary className="cursor-pointer break-words font-medium">{row.item.title} · 没有变化</summary><div className="mt-3"><RequirementChange row={row} value={value} showTitle={false} /></div></details>)}</div>
    <details className="min-w-0 border-t border-slate-200 pt-3"><summary className="w-fit cursor-pointer py-1 text-indigo-700">两次报告、材料版本与比较范围</summary>
      <div className="space-y-3 pt-3 leading-6 [overflow-wrap:anywhere]">
        <div className="flex flex-wrap gap-4"><Link className="text-indigo-700 underline" href={`/reports/${value.baseId}`}>基准报告 · {new Date(base.createdAt).toLocaleString("zh-CN")}</Link><Link className="text-indigo-700 underline" href={`/reports/${value.targetId}`}>当前报告 · {new Date(current.createdAt).toLocaleString("zh-CN")}</Link></div>
        <p>变化背景：{value.contextChanges.map(key => GROWTH_CHANGES[key] ?? key).join("、") || "未记录背景变化"}。材料版本发生变化，不代表每一条引用或判断都改变。</p>
        {[{label: "基准材料", rows: value.baseMaterials}, {label: "当前材料", rows: value.targetMaterials}].map(side => <div key={side.label}><h3 className="font-medium">{side.label}</h3><ul>{side.rows.map(m => <li key={`${m.kind}-${m.id}`}>{m.title} · 第 {m.versionNumber} 版<details className="text-xs text-slate-600"><summary className="w-fit cursor-pointer">版本校验信息</summary><p>{m.id} · {m.contentHash}</p></details></li>)}</ul></div>)}
        <p>测试代码引用与运行记录引用分别展示。上传的测试输出仍需核对内容及源码版本，不是平台独立执行结果；未再展示的引用仍可在基准报告中查看。</p>
        <ul className="space-y-1 text-xs text-slate-600">{value.limitations.map(note => <li key={note}>{note}</li>)}</ul>
      </div>
    </details>
  </div>;
}
