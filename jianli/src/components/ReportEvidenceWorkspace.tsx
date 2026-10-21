"use client";

import Link from "next/link";
import { useState } from "react";
import type { MatchReport } from "@/lib/api/domain";
import { ACTION_SOURCE_LABELS, distinctActionText, evidenceWorkspace } from "@/lib/evidence-workspace";
import ActionPlan from "./ActionPlan";
import EvidenceLink from "./EvidenceLink";

const GROUPS = [
  { key: "supported", label: "有证据支持" },
  { key: "partial", label: "部分支持" },
  { key: "gaps", label: "待补材料" },
  { key: "other", label: "未覆盖或需复核" },
] as const;
type Group = typeof GROUPS[number]["key"];

export function ReportActionLayer({ report, role }: { report: MatchReport; role?: string }) {
  return role === "student" ? <ReportEvidenceWorkspace key={report.id} report={report} /> : <ActionPlan actions={report.actionPlan} />;
}

export default function ReportEvidenceWorkspace({ report }: { report: MatchReport }) {
  const state = evidenceWorkspace(report.items);
  const [expanded, setExpanded] = useState<Group | null>(() =>
    (["gaps", "partial", "other", "supported"] as const).find(key => state[key].length > 0) ?? "gaps"
  );
  const actions = new Map((report.actionPlan ?? []).map(action => [action.requirementId, action]));
  const materialVersions = (report.materials ?? [])
    .map(material => {
      const kind = material.kind === "resume" ? "简历" : material.kind === "project" ? "项目" : material.kind;
      return `${material.title || kind}（${kind} v${material.versionNumber}）`;
    })
    .join(" · ");
  const openCount = state.gaps.length + state.partial.length + state.other.length;

  return <section aria-labelledby="evidence-workspace-title" className="panel min-w-0 space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 id="evidence-workspace-title" className="text-lg font-semibold">下一步补证计划</h2>
        <p className="mt-1 text-sm leading-6 text-slate-600">选择一组要求查看缺口，按需核对证据或开始补证。补证不影响你直接投递本份报告。</p>
        {materialVersions && <p className="mt-2 break-words text-xs leading-5 text-slate-500">本报告固定材料：{materialVersions}。补证或上传新版不会替换本报告。</p>}
        <p className="mt-2 text-sm leading-6 text-slate-700">
          {report.items.length === 0
            ? "下一步：暂无逐项结果，请先核对报告状态。"
            : openCount > 0
            ? `下一步：可核对 ${openCount} 项待补、部分支持或需复核的要求，也可直接投递当前报告；若补充材料，请生成新报告后再选择投递版本。`
            : "下一步：核对关键引用后，可直接投递本报告；如材料更新，请生成新报告再决定。"}
        </p>
      </div>
      <Link href="#report-comparison" className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">查看版本变化 →</Link>
    </div>
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="按已保存的材料支持状态查看要求">
      {GROUPS.map(({ key, label }) => <button key={key} type="button"
        id={`evidence-group-${key}`} aria-expanded={expanded === key} aria-controls={`evidence-panel-${key}`}
        onClick={() => setExpanded(current => current === key ? null : key)}
        className={`min-h-20 rounded-xl border p-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 ${expanded === key ? "border-indigo-600 bg-indigo-50 text-indigo-950" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}>
        <span className="block text-xs leading-5">{label}</span>
        <span className="mt-1 block text-2xl font-semibold">{state[key].length}<span className="ml-1 text-xs font-normal">项</span></span>
        <span className="mt-1 block text-xs">{expanded === key ? "收起" : "展开"}</span>
      </button>)}
    </div>
    {GROUPS.map(({ key, label }) => <div key={key} id={`evidence-panel-${key}`} role="region"
      aria-labelledby={`evidence-group-${key}`} hidden={expanded !== key}>
      {expanded === key && <>
        <h3 className="mb-3 font-medium">{label} · {state[key].length} 项</h3>
        {state[key].length === 0 ? <p className="rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">当前没有标记为“{label}”的要求，可以选择其他分组查看。</p> : <ul className="space-y-3">
          {state[key].map(item => {
            const action = actions.get(item.requirementId);
            const gap = item.evidenceLevelGap?.trim() || item.explanation?.trim() || "该项暂无已保存的缺口说明，请核对原要求与材料。";
            const text = action ? distinctActionText(action, gap) : null;
            const allowed = new Set(item.evidenceList.map(evidence => evidence.citationId));
            const citations = [...new Set(action?.citationIds ?? [])].filter(citation => allowed.has(citation));
            return <li key={item.requirementId} className="min-w-0 rounded-xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h4 className="min-w-0 break-words font-medium">{item.requirementTitle}</h4>
                {action && <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{ACTION_SOURCE_LABELS[action.source] ?? "来源未标注"}</span>}
              </div>
              <p className="mt-1 text-xs text-slate-500">岗位权重 {item.weight} / 5</p>
              <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-600">{gap}</p>
              {text?.advice && <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6"><strong>建议行动：</strong>{text.advice}</p>}
              {text?.gap && <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-600"><strong>建议对应缺口：</strong>{text.gap}</p>}
              {citations.length > 0 && <div className="mt-2 flex flex-wrap gap-3">{citations.map(citation => <EvidenceLink key={citation} citationId={citation} className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">查看引用 {citation}</EvidenceLink>)}</div>}
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2">
                <Link className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline" href={`#requirement-${item.requirementId}`}>核对来源与逐项解释</Link>
                {(key === "gaps" || key === "partial") && <Link className="btn-secondary min-h-11" href={`#growth-${item.requirementId}`}>从这条缺口开始补证 →</Link>}
              </div>
            </li>;
          })}
        </ul>}
      </>}
    </div>)}
    {expanded === null && <p className="text-sm text-slate-600">选择上方状态，展开对应要求。</p>}
    <details className="border-t border-slate-200 pt-3 text-sm">
      <summary className="cursor-pointer py-2 font-medium text-slate-700">补证步骤与投递说明</summary>
      <p className="mt-2 leading-6 text-slate-600">核对一条缺口 → 补充并保存新版材料 → 主动生成新报告，再查看逐项变化。</p>
      <p className="mt-2 leading-6 text-slate-600">已投递时，企业查看的是投递当时的固定报告。补证任务和新报告不会自动替换该快照，也不会自动向企业发送内容。</p>
      <Link className="mt-2 inline-flex min-h-11 items-center text-indigo-700 underline" href="/growth">查看我的补证任务 →</Link>
    </details>
  </section>;
}
