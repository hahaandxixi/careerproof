"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { navigateEvidenceFragment, revealEvidenceAnchor } from "@/lib/evidence-anchor";

type Section = { id: string; label: string; content: ReactNode };

/** Report-level navigation is independent of requirement selection and source disclosures.
 * All panels remain mounted: switching must not reset consent, review or follow-up drafts.
 * The shared paper header stays outside the hidden sections so all four views retain identity. */
export default function ReportSections({ sections, versions, header }: {
  sections: Section[]; versions: ReactNode; header?: ReactNode;
}) {
  const [active, setActive] = useState(sections[0].id);
  const root = useRef<HTMLDivElement>(null);
  const sectionsRef = useRef(sections);
  sectionsRef.current = sections;
  const scrollFrame = useRef(0);
  const recoverReadingStart = useRef<() => void>(() => {});

  useEffect(() => {
    const rootElement = root.current;
    const siteHeader = document.querySelector<HTMLElement>(".site-header");
    const syncOffset = () => {
      if (!rootElement || !siteHeader) return;
      rootElement.style.setProperty(
        "--report-sticky-offset",
        `${Math.ceil(siteHeader.getBoundingClientRect().height + 16)}px`,
      );
    };
    syncOffset();
    window.addEventListener("resize", syncOffset);
    const observer = typeof ResizeObserver === "function" && siteHeader
      ? new ResizeObserver(syncOffset) : null;
    if (observer && siteHeader) observer.observe(siteHeader);
    return () => {
      window.removeEventListener("resize", syncOffset);
      observer?.disconnect();
    };
  }, []);

  useEffect(() => {
    const reportRoot = root.current;
    const stickyOffset = () => {
      const measured = root.current
        ? Number.parseFloat(getComputedStyle(root.current).getPropertyValue("--report-sticky-offset"))
        : Number.NaN;
      if (Number.isFinite(measured)) return measured;
      return (document.querySelector<HTMLElement>(".site-header")?.getBoundingClientRect().height ?? 0) + 16;
    };
    const paper = () => reportRoot?.querySelector<HTMLElement>("[data-report-paper]");
    const canScroll = () => typeof window.scrollTo === "function";
    const scrollY = () => Number(window.scrollY) || 0;

    const scrollReadingStart = () => {
      const element = paper();
      if (!element || !canScroll()) return;
      const offset = stickyOffset();
      const top = element.getBoundingClientRect().top;
      // Only pull the reading start back under the fixed bar when the user is
      // already deep in the report. A switch near the top must not move the page.
      if (top >= offset - 1) return;
      const y = Math.max(0, scrollY() + top - offset);
      window.scrollTo({ top: y, behavior: "auto" });
    };
    recoverReadingStart.current = scrollReadingStart;

    const focusTarget = (target: HTMLElement) => {
      const heading = target.id.startsWith("requirement-")
        ? target.querySelector<HTMLElement>("h3") : null;
      const node = heading ?? target;
      if (!heading) target.tabIndex = -1;
      node?.focus?.({ preventScroll: true });
    };

    const scrollDeepTarget = (target: HTMLElement) => {
      if (!canScroll()) return;
      const offset = stickyOffset();
      const y = Math.max(0, scrollY() + target.getBoundingClientRect().top - offset);
      window.scrollTo({ top: y, behavior: "auto" });
    };

    const revealAndPosition = (id: string, attempt = 0) => {
      const target = revealEvidenceAnchor(id);
      const panel = target?.closest<HTMLElement>("[data-report-section]");
      if (panel) flushSync(() => setActive(panel.id));
      if (!target) return;
      const rendered = typeof target.getClientRects !== "function"
        || target.getClientRects().length > 0;
      if (!rendered && attempt < 3) {
        scrollFrame.current = requestAnimationFrame(() => revealAndPosition(id, attempt + 1));
        return;
      }
      scrollDeepTarget(target);
      focusTarget(target);
    };

    const restore = () => {
      cancelAnimationFrame(scrollFrame.current);
      let id: string;
      try { id = decodeURIComponent(window.location.hash.slice(1)); } catch { return; }
      if (!id) {
        flushSync(() => setActive(sectionsRef.current[0].id));
        return;
      }
      const section = sectionsRef.current.find(item => item.id === id);
      if (section) {
        flushSync(() => setActive(section.id));
        scrollFrame.current = requestAnimationFrame(scrollReadingStart);
        return;
      }
      const target = document.getElementById(id);
      const panel = target?.closest<HTMLElement>("[data-report-section]");
      if (panel) flushSync(() => setActive(panel.id));
      // Let the newly active panel render before measuring the deep anchor;
      // hidden source/article states are retried inside revealAndPosition.
      scrollFrame.current = requestAnimationFrame(() => revealAndPosition(id));
    };

    const reveal = (event: Event) => {
      const target = (event as CustomEvent<HTMLElement>).detail;
      const panel = target?.closest<HTMLElement>("[data-report-section]");
      if (panel && reportRoot?.contains(panel)) flushSync(() => setActive(panel.id));
    };

    window.addEventListener("careerproof:reveal-evidence", reveal);
    window.addEventListener("hashchange", restore);
    // Native fragment scrolling runs after hydration on a full refresh. Re-apply
    // the report's measured offset once load/pageshow has settled.
    window.addEventListener("load", restore);
    window.addEventListener("pageshow", restore);
    const frame = requestAnimationFrame(restore);
    return () => {
      cancelAnimationFrame(frame);
      cancelAnimationFrame(scrollFrame.current);
      window.removeEventListener("careerproof:reveal-evidence", reveal);
      window.removeEventListener("hashchange", restore);
      window.removeEventListener("load", restore);
      window.removeEventListener("pageshow", restore);
      recoverReadingStart.current = () => {};
    };
  }, []);

  return <div ref={root} className="report-document-grid" data-report-sections>
    <nav className="report-section-directory" aria-label="本报告目录">
      <p className="text-base text-slate-600">本报告</p>
      {sections.map(section => <a key={section.id} href={`#${section.id}`} aria-current={active === section.id ? "location" : undefined} aria-controls={section.id} className={active === section.id ? "report-section-active" : undefined} onClick={event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        flushSync(() => setActive(section.id));
        const nextHash = `#${section.id}`;
        if (window.location.hash === nextHash) {
          // Same-fragment click has no hashchange; still recover the reading
          // start when the user is deep in the previous panel.
          recoverReadingStart.current();
        } else {
          navigateEvidenceFragment(nextHash);
        }
      }}>{section.label}</a>)}
      <div className="report-directory-versions">{versions}</div>
    </nav>
    <div className="report-paper min-w-0" data-report-paper>
      {header}
      {sections.map(section => <section key={section.id} id={section.id} data-report-section="" tabIndex={-1} aria-label={section.label} hidden={active !== section.id} className="report-content-section">{section.content}</section>)}
    </div>
  </div>;
}
