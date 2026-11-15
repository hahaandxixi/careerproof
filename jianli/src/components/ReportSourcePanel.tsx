"use client";

import { useEffect, useState } from "react";
import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { adoptedReportExplanation, type WorkspaceFilter } from "@/lib/report-workspace";
import { materialReportContext } from "@/lib/material-report-link";
import { compactSourceLabel, sourceLocationId } from "@/lib/source-label";
import EvidenceSnippet from "./EvidenceSnippet";
import EvidenceLink from "./EvidenceLink";
import { SourceIdentityDetails } from "./SourceIdentity";
import { sourceLimit } from "@/lib/source-limits";

export default function ReportSourcePanel({ report, item, canOpenMaterial = false, filter, origin }: { report: MatchReport; item: ReportItem; canOpenMaterial?: boolean; filter?: WorkspaceFilter; origin?: string }) {
  const adopted = !!adoptedReportExplanation(report, item);
  const first = adopted ? item.evidenceList.findIndex(source => !!source.citationId && item.aiCitationIds.includes(source.citationId)) : 0;
  const [sourceIndex, setSourceIndex] = useState(Math.max(0, first));
  const selected = Math.min(sourceIndex, Math.max(0, item.evidenceList.length - 1));

  useEffect(() => {
    const selectAnchor = (anchor: string) => {
      const index = item.evidenceList.findIndex((source, i) => sourceLocationId(item.requirementId, source, i) === anchor);
      if (index >= 0) setSourceIndex(index);
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

  return <section className="report-source-panel min-w-0" aria-label={item.skill + "的证据来源"}>
    {item.evidenceList.length ? <div>{item.evidenceList.map((source, index) => {
      const label = compactSourceLabel(source, report.materials);
      const limit = sourceLimit(report, source);
      const locationId = sourceLocationId(item.requirementId, source, index);
      const ownedVersion = report.materials.some(material => material.kind === "project" && material.id === source.projectVersionId);
      const params = materialReportContext(report.id, item.requirementId, locationId, filter, origin);
      params.set("lineStart", String(source.lineStart));
      params.set("lineEnd", String(source.lineEnd));
      if (source.projectFileId) params.set("fileId", source.projectFileId);
      const fileHref = canOpenMaterial && ownedVersion && source.projectFileId
        ? `/materials/project/${source.projectVersionId}?${params}`
        : null;
      return <article key={locationId} id={locationId} hidden={selected !== index} aria-label={"来源 " + (index + 1) + "：" + label.fileName} className="report-source-reader scroll-mt-24">
        <header className="source-reader-heading">
          <div className="min-w-0">
            <h4 className="break-words text-xl font-semibold">{label.fileName}</h4>
            <p className="mt-1 break-words text-sm">{item.skill} · {label.material} · 第 {source.lineStart}–{source.lineEnd} 行{source.provenance === "reference" ? " · 第三方参考，不计评级" : ""}</p>
            {limit && <p className="source-reader-limit">{limit.label} · {limit.detail}</p>}
          </div>
        </header>
        <div className="source-reader-code">
          {limit?.readable !== false && <EvidenceSnippet evidence={source} materials={report.materials} showContextNote={false} theme="dark" />}
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
    {item.evidenceList.length > 1 && <details className="mt-2 text-sm">
      <summary className="disclosure">其他来源</summary>
      <ul className="mt-1 space-y-2">{item.evidenceList.map((source, index) => {
        if (selected === index) return null;
        const locationId = sourceLocationId(item.requirementId, source, index);
        const label = compactSourceLabel(source, report.materials);
        return <li key={locationId} className="break-words"><EvidenceLink targetId={locationId} className="action-link">{label.fileName} · {source.lineStart}–{source.lineEnd} 行 · {label.material}</EvidenceLink></li>;
      })}</ul>
    </details>}
  </section>;
}
