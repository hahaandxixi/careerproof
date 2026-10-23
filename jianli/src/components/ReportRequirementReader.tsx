"use client";

import { Children, useEffect, useState, type ReactNode } from "react";
import type { ReportItem } from "@/lib/api/domain";
import { revealEvidenceAnchor } from "@/lib/evidence-anchor";
import { initialReportRequirement, reportAnchorId, reportEntryRequirement, requirementForReportAnchor } from "@/lib/report-reader";
import { VERDICT_LABELS } from "@/lib/verdict-display.js";

/** All saved articles remain mounted, including their source anchors and private drafts. */
export default function ReportRequirementReader({ items, children }: { items: ReportItem[]; children: ReactNode }) {
  const [entry, setEntry] = useState<{ selected: string | null; anchor: string | null; revision: number }>(() => ({
    selected: initialReportRequirement(items), anchor: null, revision: 0,
  }));
  useEffect(() => {
    const select = (hash: string, search = "") => {
      const selected = reportEntryRequirement(items, hash, search);
      if (!selected) return;
      const anchor = reportAnchorId(hash);
      setEntry(previous => ({ selected, anchor: requirementForReportAnchor(items, anchor) ? anchor : `growth-${selected}`, revision: previous.revision + 1 }));
    };
    const fromLocation = () => select(window.location.hash, window.location.search);
    const fromLink = (event: MouseEvent) => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      const href = link?.getAttribute("href");
      // Capture local links too: repeating a fragment, or Next navigation, need not emit hashchange.
      if (href?.startsWith("#") && reportEntryRequirement(items, href)) {
        // Capture the original destination: selecting can rerender mobile prev/next links
        // before the browser reads their default-action href, otherwise one click skips an item.
        event.preventDefault();
        if (window.location.hash !== href) window.location.hash = href;
        select(href);
      }
    };
    fromLocation();
    window.addEventListener("hashchange", fromLocation);
    document.addEventListener("click", fromLink, true);
    return () => { window.removeEventListener("hashchange", fromLocation); document.removeEventListener("click", fromLink, true); };
  }, [items]);
  useEffect(() => {
    if (!entry.anchor) return;
    // Run after the selected panel is visible; opening source details before that would scroll a hidden node.
    const frame = requestAnimationFrame(() => {
      const target = revealEvidenceAnchor(entry.anchor!);
      if (entry.anchor!.startsWith("requirement-")) {
        const heading = target?.querySelector?.("h3") as HTMLElement | null;
        heading?.focus?.({ preventScroll: true });
      }
      target?.scrollIntoView({ block: "start" });
    });
    return () => cancelAnimationFrame(frame);
  }, [entry]);

  const articles = Children.toArray(children);
  const currentIndex = Math.max(0, items.findIndex(item => item.requirementId === entry.selected));
  const current = items[currentIndex];
  if (!items.length) return <section className="panel text-sm text-slate-600">本报告尚无逐项要求，请核对处理记录。</section>;
  return <section aria-labelledby="report-requirements-title" className="min-w-0 space-y-4">
    <div><h2 id="report-requirements-title" className="section-title">逐项查看岗位要求</h2><p className="mt-1 text-sm leading-6 text-slate-600">选择一项，核对判断、来源和下一步；引用链接会直接打开对应要求。</p></div>
    <nav className="space-y-2 rounded-xl border border-slate-200 bg-white p-3 lg:hidden" aria-label="手机逐项阅读导航">
      <p className="text-xs font-medium text-indigo-800" aria-live="polite">第 {currentIndex + 1} / {items.length} 项</p>
      <p className="break-words text-sm font-semibold leading-6">{current.requirementTitle}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {currentIndex > 0 ? <a className="btn-secondary min-h-11" href={`#requirement-${items[currentIndex - 1].requirementId}`}>上一项</a> : <span className="text-xs text-slate-600">已是第一项</span>}
        {currentIndex < items.length - 1 ? <a className="btn-secondary min-h-11" href={`#requirement-${items[currentIndex + 1].requirementId}`}>下一项</a> : <span className="text-xs text-slate-600">已是最后一项</span>}
        <details className="w-full"><summary className="cursor-pointer py-2 text-sm text-indigo-700">展开全部要求（{items.length}）</summary><ol className="space-y-2 pt-2">{items.map((item,index) => <li key={item.requirementId}><a className="block rounded-lg border border-slate-200 p-3 text-sm leading-6" href={`#requirement-${item.requirementId}`} aria-current={entry.selected === item.requirementId ? "true" : undefined} onClick={event => event.currentTarget.closest("details")?.removeAttribute("open")}>{index + 1}. {item.requirementTitle}<span className="block text-xs text-slate-600">{VERDICT_LABELS[item.verdict] ?? item.verdict} · {item.evidenceList.length} 条来源</span></a></li>)}</ol></details>
      </div>
    </nav>
    <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
      <nav aria-label="报告中的岗位要求" className="hidden min-w-0 lg:sticky lg:top-24 lg:block">
        <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">{items.map((item, index) => {
          const selected = entry.selected === item.requirementId;
          return <li key={item.requirementId} className="min-w-0"><a href={`#requirement-${item.requirementId}`}
            aria-current={selected ? "true" : undefined}
            className={`block min-h-11 rounded-xl border p-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 ${selected ? "border-indigo-600 bg-indigo-50 text-indigo-950" : "border-slate-200 bg-white text-slate-700 hover:border-indigo-300 hover:bg-slate-50"}`}>
            <span className="flex gap-2"><span className="shrink-0 text-sm">{index + 1}.</span><span className="min-w-0 break-words text-sm font-semibold">{item.requirementTitle}</span></span>
            <span className="mt-2 block text-xs leading-5">{VERDICT_LABELS[item.verdict] ?? item.verdict} · {item.evidenceList.length} 条来源</span>
            {selected && <span className="mt-1 block text-xs font-medium">正在查看</span>}
          </a></li>;
        })}</ol>
      </nav>
      <div className="min-w-0">{items.map((item, index) => <div key={item.requirementId} hidden={entry.selected !== item.requirementId}>{articles[index]}</div>)}</div>
    </div>
  </section>;
}
