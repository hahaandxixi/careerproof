"use client";

import { Children, useEffect, useState, type ReactNode } from "react";
import type { ReportItem } from "@/lib/api/domain";
import { revealEvidenceAnchor } from "@/lib/evidence-anchor";
import { initialReportRequirement, reportAnchorId, reportEntryRequirement, requirementForReportAnchor } from "@/lib/report-reader";
import { evidenceWorkspace } from "@/lib/evidence-workspace";
import { filterForRequirement, initialWorkspaceFilter, requirementSummary, workspaceRequirements, workspaceStatusLabel, type WorkspaceFilter } from "@/lib/report-workspace";

/** All saved articles remain mounted, including their source anchors and private drafts. */
export default function ReportRequirementReader({ items, children }: { items: ReportItem[]; children: ReactNode }) {
  const [entry, setEntry] = useState<{ selected: string | null; anchor: string | null; revision: number; filter: WorkspaceFilter }>(() => ({
    selected: initialReportRequirement(items), anchor: null, revision: 0, filter: initialWorkspaceFilter(items),
  }));
  useEffect(() => {
    const select = (hash: string, search = "") => {
      const selected = reportEntryRequirement(items, hash, search);
      if (!selected) return;
      const anchor = reportAnchorId(hash);
      setEntry(previous => ({ filter: filterForRequirement(items, previous.filter, selected), selected, anchor: requirementForReportAnchor(items, anchor) ? anchor : `growth-${selected}`, revision: previous.revision + 1 }));
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
  if (!items.length) return <section className="panel text-sm text-slate-600">本报告尚无逐项要求，请核对处理记录。</section>;
  const state = evidenceWorkspace(items);
  const visible = workspaceRequirements(items, entry.filter);
  const filters: { key: WorkspaceFilter; label: string; count: number }[] = [
    { key: "priority", label: "优先处理", count: state.priorities.length + state.other.length },
    { key: "all", label: "全部要求", count: items.length },
    { key: "supported", label: "有证据支持", count: state.supported.length },
    { key: "partial", label: "部分支持", count: state.partial.length },
    { key: "gaps", label: "待补材料", count: state.gaps.length },
    { key: "other", label: "未覆盖或需复核", count: state.other.length },
  ];
  const changeFilter = (filter: WorkspaceFilter) => {
    const list = workspaceRequirements(items, filter);
    const selected = list.some(item => item.requirementId === entry.selected) ? entry.selected : list[0]?.requirementId ?? null;
    setEntry(previous => ({ ...previous, filter, selected, anchor: null }));
    // Preserve the current requirement across refresh without moving focus away from the filter.
    if (selected && selected !== entry.selected) window.history.pushState(null, "", `#requirement-${selected}`);
  };
  return <section aria-labelledby="report-requirements-title" className="min-w-0 space-y-4">
    <header><h2 id="report-requirements-title" className="section-title">岗位匹配与补证工作台</h2>
      <p className="mt-1 text-sm leading-6 text-slate-600">共 {items.length} 项要求。先找待处理项，再核对依据或开始补证；也可直接投递当前报告。</p>
    </header>
    <div className="flex flex-wrap gap-2" role="group" aria-label="按已保存的材料支持状态筛选">
      {filters.map(filter => <button key={filter.key} type="button" aria-pressed={entry.filter === filter.key}
        onClick={() => changeFilter(filter.key)} className={`min-h-11 rounded-lg border px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 ${entry.filter === filter.key ? "border-indigo-600 bg-indigo-50 text-indigo-950" : "border-slate-200 bg-white text-slate-600 hover:border-indigo-300"}`}>
        {filter.label}<span className="ml-2 tabular-nums">{filter.count}</span>
      </button>)}
    </div>
    <p className="text-xs text-slate-600" role="status">当前筛选 {visible.length} 项{entry.selected ? ` · 正在查看${items.find(item => item.requirementId === entry.selected)?.skill ?? "所选要求"}` : ""}</p>
    <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[minmax(16rem,0.52fr)_minmax(0,1fr)]">
      <nav aria-label="报告中的岗位要求" className="min-w-0">
        {visible.length ? <ol className="space-y-2">{visible.map(item => {
          const selected = entry.selected === item.requirementId;
          return <li key={item.requirementId} className="min-w-0"><a href={`#requirement-${item.requirementId}`} aria-current={selected ? "true" : undefined}
            className={`block min-h-11 border-l-2 px-3 py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 ${selected ? "border-indigo-600 bg-indigo-50/60 text-indigo-950" : "border-slate-200 bg-white text-slate-700 hover:border-indigo-300 hover:bg-slate-50"}`}>
            <span className="block break-words text-sm font-semibold leading-6">{item.requirementTitle}</span>
            <span className="mt-1 block text-xs leading-6">{workspaceStatusLabel(item)} · 岗位权重 {item.weight}/5{selected ? " · 正在查看" : ""}</span>
            <span className="mt-1 block break-words text-xs leading-5 text-slate-500">{requirementSummary(item)}</span>
          </a></li>;
        })}</ol> : <p className="rounded-lg bg-slate-50 p-4 text-sm leading-6 text-slate-600">当前没有这一类要求。<button type="button" className="ml-2 min-h-11 text-indigo-700 underline" onClick={() => changeFilter("all")}>查看全部要求</button></p>}
        <nav className="mt-3 flex flex-wrap gap-2 lg:hidden" aria-label="手机逐项阅读导航">
          {currentIndex > 0 && <a className="btn-secondary min-h-11" href={`#requirement-${items[currentIndex - 1].requirementId}`}>上一项</a>}
          {currentIndex < items.length - 1 && <a className="btn-secondary min-h-11" href={`#requirement-${items[currentIndex + 1].requirementId}`}>下一项</a>}
          {entry.filter !== "all" && <button type="button" className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline" onClick={() => changeFilter("all")}>展开全部要求（{items.length}）</button>}
        </nav>
      </nav>
      <div className="min-w-0">{!visible.length && <p className="text-sm text-slate-500">选择其他筛选查看判断与行动。</p>}{items.map((item, index) => <div key={item.requirementId} hidden={entry.selected !== item.requirementId}>{articles[index]}</div>)}</div>
    </div>
  </section>;
}
