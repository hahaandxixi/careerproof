"use client";
import { useEffect, useState } from "react";
import type { ReportItem } from "@/lib/api/domain";
import { initialReportRequirement } from "@/lib/report-reader";
import { workspaceStatusLabel } from "@/lib/report-workspace";

import { reportStatusTone } from "@/lib/evidence-workspace";

/** Compact requirement heatmap from saved fields; no score or invented capability. */
export default function ReportRequirementHeatmap({ items, selectedRequirementId }: { items: ReportItem[]; selectedRequirementId?: string | null }) {
  const read = () => {
    const id = window.location.hash.match(/^#requirement-(.+)$/)?.[1];
    return id && items.some(item => item.requirementId === id) ? id : initialReportRequirement(items);
  };
  const [selected, setSelected] = useState<string | null>(() => items[0] ? initialReportRequirement(items) : null);
  useEffect(() => {
    if (selectedRequirementId !== undefined) setSelected(selectedRequirementId);
  }, [selectedRequirementId]);
  useEffect(() => {
    if (selectedRequirementId !== undefined) return;
    const sync = () => setSelected(read());
    sync();
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => { window.removeEventListener("hashchange", sync); window.removeEventListener("popstate", sync); };
  }, [items, selectedRequirementId]);
  return <section className="report-heatmap" aria-label="岗位要求材料状态热力图">
    <div className="report-heatmap-head"><div><h2>要求状态热力图</h2><p>每行是一项真实要求；列分别表示简历声明、可定位来源与已保存判断。</p></div>
      <div className="report-heatmap-legend" aria-label="状态图例"><span data-tone="supported">有证据支持</span><span data-tone="partial">部分支持</span><span data-tone="gap">待补或仅声明</span><span data-tone="other">暂不支持或需复核</span></div></div>
    <div className="report-heatmap-grid" role="table">
      <div className="report-heatmap-row report-heatmap-title" role="row"><span role="columnheader">岗位要求</span><span role="columnheader">简历声明</span><span role="columnheader">可定位来源</span><span role="columnheader">当前判断</span></div>
      {items.map(item => <a key={item.requirementId} href={`#requirement-${item.requirementId}`} className={`report-heatmap-row ${selected === item.requirementId ? "is-selected" : ""}`} role="row" data-tone={reportStatusTone(item)} aria-current={selected === item.requirementId ? "true" : undefined}>
        <strong role="cell">{item.skill || item.requirementTitle}</strong>
        <span role="cell" data-kind="claim" data-state={item.claimed ? "on" : "off"}>{item.claimed ? "有声明" : "未识别"}</span>
        <span role="cell" data-kind="source" data-state={item.evidenceList.length ? "on" : "off"}>{item.evidenceList.length ? `${item.evidenceList.length} 处` : "无引用"}</span>
        <span role="cell" className="report-heatmap-verdict">{workspaceStatusLabel(item)}</span>
      </a>)}
    </div>
  </section>;
}

