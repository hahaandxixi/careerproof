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
  const [entry, setEntry] = useState({ index: Math.max(0, first), anchor: "", revision: 0, opened: true });
  // The reader is a persistent part of the report column, not a floating panel.
  // Keep the existing state for source switching, but never render it as a modal-like closeable card.
  const selected = Math.min(entry.index, Math.max(0, item.evidenceList.length - 1));

  useEffect(() => {
    const selectAnchor = (anchor: string) => {
      const index = item.evidenceList.findIndex((source, i) => sourceLocationId(item.requirementId, source, i) === anchor);
      if (index >= 0) setEntry(old => ({ index, anchor, revision: old.revision + 1, opened: true }));
    };
    const location = () => {
      try { selectAnchor(decodeURIComponent(window.location.hash.slice(1))); }
      catch { /* Invalid historical fragments do not identify a source. */ }
    };
    const click = (event: MouseEvent) => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const href = event.target instanceof Element ? event.target.closest("a[href]")?.getAttribute("href") : null;
      if (href?.startsWith("#")) {
        try { selectAnchor(decodeURIComponent(href.slice(1))); }
        catch { /* Keep the current source. */ }
      }
    };
    location();
    window.addEventListener("hashchange", location);
    window.addEventListener("popstate", location);
    document.addEventListener("click", click, true);
    return () => {
      window.removeEventListener("hashchange", location);
      window.removeEventListener("popstate", location);
      document.removeEventListener("click", click, true);
    };
  }, [item]);

  const choose = (index: number) => setEntry(old => ({ index, anchor: "", revision: old.revision + 1, opened: true }));
  return <section className="report-source-panel min-w-0" aria-label={item.skill + "的证据来源"}>
    {item.evidenceList.length > 0 && <div className="source-reader-toolbar">
      <p className="source-reader-title">引用原文 · {item.evidenceList.length} 处</p>
      {item.evidenceList.length > 1 && <div className="flex min-w-0 flex-1 items-end gap-2">
        <label className="min-w-0 flex-1 text-sm">选择来源
          <select className="field mt-1" value={selected} onChange={event => choose(Number(event.target.value))}>
            {item.evidenceList.map((source, index) => {
              const label = compactSourceLabel(source, report.materials);
              return <option key={sourceLocationId(item.requirementId, source, index)} value={index}>{index + 1}. {label.fileName} · {source.lineStart}–{source.lineEnd}行 · {label.material}{sourceLimit(report, source) ? " · " + sourceLimit(report, source)?.label : ""}</option>;
            })}
          </select>
        </label>
        <button type="button" className="btn-quiet" aria-label="上一个来源" disabled={selected === 0} onClick={() => choose(selected - 1)}>上一处</button>
        <button type="button" className="btn-quiet" aria-label="下一个来源" disabled={selected === item.evidenceList.length - 1} onClick={() => choose(selected + 1)}>下一处</button>
      </div>}
    </div>}
    {item.evidenceList.length ? <div>{item.evidenceList.map((source, index) => {
      const label = compactSourceLabel(source, report.materials);
      const limit = sourceLimit(report, source);
      const locationId = sourceLocationId(item.requirementId, source, index);
      const ownedVersion = report.materials.some(material => material.kind === "project" && material.id === source.projectVersionId);
      const fileHref = ownedVersion && source.projectFileId
        ? "/materials/project/" + source.projectVersionId + "?" + new URLSearchParams({ fileId: source.projectFileId, lineStart: String(source.lineStart), lineEnd: String(source.lineEnd) })
        : null;
      return <article key={locationId} id={locationId} hidden={!entry.opened || selected !== index} aria-label={"来源 " + (index + 1) + "：" + label.fileName} className="report-source-reader scroll-mt-24">
        <header className="source-reader-heading">
          <div className="min-w-0">
            <h4 className="break-words text-xl font-semibold">{label.fileName}</h4>
            <p className="mt-1 break-words text-sm">{item.skill} · {label.material} · 第 {source.lineStart}–{source.lineEnd} 行{source.provenance === "reference" ? " · 第三方参考，不计评级" : ""}</p>
            {limit && <p className="source-reader-limit">{limit.label} · {limit.detail}</p>}
          </div>
        </header>
        <div className="source-reader-code">
          {limit?.readable !== false && <EvidenceSnippet evidence={source} materials={report.materials} showContextNote={false} />}
        </div>
        <div className="source-reader-details">
          {fileHref && <a href={fileHref} className="action-link">查看完整文件 ↗</a>}
          <SourceIdentityDetails source={source}>
            <p className="mt-2 break-words leading-6">{source.explanation}</p>
            {source.contextNote && <p className="mt-2">{source.contextNote}</p>}
          </SourceIdentityDetails>
        </div>
      </article>;
    })}</div> : <p className="report-source-empty">{item.verdict === "unsupported" ? "当前规则未覆盖此要求，请人工核对保存材料。" : "当前报告没有对应的可定位引用，不能据此认定没有这项能力。"}</p>}
  </section>;
}
