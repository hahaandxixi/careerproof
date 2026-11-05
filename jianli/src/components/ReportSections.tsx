"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { revealEvidenceAnchor } from "@/lib/evidence-anchor";

type Section = { id: string; label: string; content: ReactNode };

/** Report-level navigation is independent of requirement selection and source disclosures.
 * All panels remain mounted: switching must not reset consent, review or follow-up drafts. */
export default function ReportSections({ sections, versions }: { sections: Section[]; versions: ReactNode }) {
  const [active, setActive] = useState(sections[0].id);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const selectTarget = (target: HTMLElement | null) => {
      const panel = target?.closest<HTMLElement>("[data-report-section]");
      if (panel && root.current?.contains(panel)) flushSync(() => setActive(panel.id));
    };
    const reveal = (event: Event) => selectTarget((event as CustomEvent<HTMLElement>).detail);
    const restore = () => {
      let id: string;
      try { id = decodeURIComponent(window.location.hash.slice(1)); } catch { return; }
      if (!id) { setActive("report-matching"); return; }
      selectTarget(document.getElementById(id));
      const target = revealEvidenceAnchor(id);
      target?.scrollIntoView({ block: "start" });
      if (target) { target.tabIndex = -1; target.focus({ preventScroll: true }); }
    };
    window.addEventListener("careerproof:reveal-evidence", reveal);
    window.addEventListener("hashchange", restore);
    const frame = requestAnimationFrame(restore);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("careerproof:reveal-evidence", reveal);
      window.removeEventListener("hashchange", restore);
    };
  }, []);
  return <div ref={root} className="report-document-grid">
    <nav className="report-section-directory" aria-label="本报告目录">
      <p className="text-base text-slate-600">本报告</p>
      {sections.map(section => <a key={section.id} href={`#${section.id}`} aria-current={active === section.id ? "location" : undefined} aria-controls={section.id} className={active === section.id ? "report-section-active" : undefined} onClick={event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        flushSync(() => setActive(section.id));
        const panel = revealEvidenceAnchor(section.id);
        panel?.scrollIntoView({ block: "start" });
        panel?.focus({ preventScroll: true });
      }}>{section.label}</a>)}
      <div className="report-directory-versions">{versions}</div>
    </nav>
    <div className="report-paper min-w-0">
      {sections.map(section => <section key={section.id} id={section.id} data-report-section="" tabIndex={-1} aria-label={section.label} hidden={active !== section.id} className="report-content-section scroll-mt-24">{section.content}</section>)}
    </div>
  </div>;
}
