"use client";

import { Children, useEffect, useState, type ReactNode } from "react";
import type { ReportItem } from "@/lib/api/domain";
import { navigateEvidenceFragment } from "@/lib/evidence-anchor";
import { initialReportRequirement, reportAnchorId, reportEntryRequirement, requirementForReportAnchor } from "@/lib/report-reader";
import { evidenceWorkspace, nextReportGap, reportStatusTone } from "@/lib/evidence-workspace";
import { filterForRequirement, initialWorkspaceFilter, workspaceRequirements, workspaceStatusLabel, type WorkspaceFilter } from "@/lib/report-workspace";
import { reportRequirementLabels } from "@/lib/skill-radar";

type ReaderEntry = { selected: string | null; anchor: string | null; revision: number; filter: WorkspaceFilter };

/** All saved articles remain mounted, including their source anchors and private drafts.
 * When the report workspace owns the current requirement (selectedRequirementId is
 * defined) this reader mirrors it and never writes a second copy back. Without a
 * parent it keeps the standalone hash navigation used by the reader's own tests. */
export default function ReportRequirementReader({ items, children, overview, selectedRequirementId, onRequirementChange, filter: sharedFilter, onFilterChange }: {
  items: ReportItem[]; children: ReactNode; overview?: ReactNode;
  selectedRequirementId?: string | null;
  onRequirementChange?: (id: string | null) => void;
  filter?: WorkspaceFilter;
  onFilterChange?: (filter: WorkspaceFilter) => void;
}) {
  const [entry, setEntry] = useState<ReaderEntry>(() => ({
    selected: initialReportRequirement(items), anchor: null, revision: 0,
    filter: items.length <= 8 ? "all" : initialWorkspaceFilter(items),
  }));
  const controlled = selectedRequirementId !== undefined;
  const selected = controlled ? selectedRequirementId : entry.selected;
  const filter = sharedFilter ?? entry.filter;

  // Standalone rendering keeps hash/back-forward/link selection. The product report
  // supplies a controlled id and owns these listeners once.
  useEffect(() => {
    if (controlled) return;
    const select = (hash: string, search = "") => {
      const next = reportEntryRequirement(items, hash, search);
      if (!next) return;
      const anchor = reportAnchorId(hash);
      setEntry(previous => ({ filter: filterForRequirement(items, previous.filter, next), selected: next, anchor: requirementForReportAnchor(items, anchor) ? anchor : `growth-${next}`, revision: previous.revision + 1 }));
    };
    const fromLocation = () => {
      if (!window.location.hash && !new URLSearchParams(window.location.search).get("enterpriseReply")) {
        setEntry(previous => ({ selected: initialReportRequirement(items), filter: items.length <= 8 ? "all" : initialWorkspaceFilter(items), anchor: null, revision: previous.revision + 1 }));
      } else select(window.location.hash, window.location.search);
    };
    const fromLink = (event: MouseEvent) => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      const href = link?.getAttribute("href");
      // Capture the original destination: selecting can rerender index links
      // before the browser reads their default-action href.
      if (href?.startsWith("#") && reportEntryRequirement(items, href)) {
        event.preventDefault();
        navigateEvidenceFragment(href);
        select(href);
      }
    };
    const fromFilter = (event: Event) => {
      const next = (event as CustomEvent<{ filter?: WorkspaceFilter }>).detail?.filter;
      if (!next) return;
      const list = workspaceRequirements(items, next);
      const first = list[0]?.requirementId ?? null;
      setEntry(previous => ({ ...previous, filter: next, selected: first, anchor: null, revision: previous.revision + 1 }));
      if (first) window.history.replaceState(null, "", `#requirement-${first}`);
    };
    fromLocation();
    window.addEventListener("hashchange", fromLocation);
    window.addEventListener("popstate", fromLocation);
    document.addEventListener("click", fromLink, true);
    window.addEventListener("careerproof:filter-requirements", fromFilter);
    return () => {
      window.removeEventListener("hashchange", fromLocation);
      window.removeEventListener("popstate", fromLocation);
      document.removeEventListener("click", fromLink, true);
      window.removeEventListener("careerproof:filter-requirements", fromFilter);
    };
  }, [items, controlled]);

  // A deep link may point outside the active filter. Only the filter adapts; the
  // parent remains the single owner of the requirement itself.
  useEffect(() => {
    if (sharedFilter !== undefined || !controlled || !selected) return;
    if (workspaceRequirements(items, entry.filter).some(item => item.requirementId === selected)) return;
    setEntry(previous => ({ ...previous, filter: filterForRequirement(items, previous.filter, selected), anchor: null, revision: previous.revision + 1 }));
  }, [controlled, selected, items, entry.filter, sharedFilter]);

  // Standalone readers still report their selection; controlled use has no loop.
  useEffect(() => { if (!controlled) onRequirementChange?.(entry.selected); }, [controlled, entry.selected, onRequirementChange]);

  const articles = Children.toArray(children);
  if (!items.length) return <section className="panel text-sm text-slate-600">本报告尚无逐项要求，请核对处理记录。</section>;
  const state = evidenceWorkspace(items);
  const visible = workspaceRequirements(items, filter);
  const labels = reportRequirementLabels(items);
  const nextGap = nextReportGap(state.gaps, selected);
  const filters: { key: WorkspaceFilter; label: string; count: number }[] = [
    { key: "priority", label: "优先处理", count: state.priorities.length + state.other.length },
    { key: "all", label: "全部要求", count: items.length },
    { key: "supported", label: "有证据支持", count: state.supported.length },
    { key: "gaps", label: "待补或仅声明", count: state.gaps.length },
    { key: "other", label: "未覆盖或需复核", count: state.other.length },
  ];
  const changeFilter = (filter: WorkspaceFilter) => {
    if (onFilterChange) { onFilterChange(filter); return; }
    const list = workspaceRequirements(items, filter);
    const next = list.some(item => item.requirementId === selected) ? selected : list[0]?.requirementId ?? null;
    setEntry(previous => ({ ...previous, filter, selected: next, anchor: null, revision: previous.revision + 1 }));
    if (controlled) {
      onRequirementChange?.(next);
      // A zero-result filter must clear the old requirement, radar highlight and
      // source instead of leaving the previous article visible.
      navigateEvidenceFragment(next ? `#requirement-${next}` : "#report-matching");
    } else if (next && next !== selected) {
      window.history.pushState(null, "", `#requirement-${next}`);
    }
  };
  return <section id="evidence-workspace-title" aria-label="岗位要求与证据" className="report-reading-desk min-w-0 scroll-mt-24">
    <div className="report-requirement-controls min-w-0" role="group" aria-label="要求筛选与选择">
      <div className="report-index-filters" role="group" aria-label="按已保存的材料支持状态筛选">
        {filters.map(option => <button key={option.key} type="button" aria-pressed={filter === option.key} data-status={option.key}
          onClick={() => changeFilter(option.key)} className={filter === option.key ? "is-active" : ""}>
          {option.label} <strong>{option.count}</strong>
        </button>)}
      </div>
      <nav aria-label="报告中的岗位要求" className="report-index-strip min-w-0">
        {visible.length ? <ol className="report-index-chips">{visible.map(item => {
          const isSelected = selected === item.requirementId;
          return <li key={item.requirementId} className="min-w-0"><a href={`#requirement-${item.requirementId}`} aria-current={isSelected ? "true" : undefined} title={`${item.requirementTitle} · ${workspaceStatusLabel(item)}`}
            className="report-index-chip">
            <span className={`report-index-dot tone-${reportStatusTone(item)}`} aria-hidden="true" />
            <span className="report-index-chip-name">{labels.get(item.requirementId)?.label}</span>
            <span className="sr-only">，{workspaceStatusLabel(item)}</span>
          </a></li>;
        })}</ol> : <p className="report-index-empty">当前没有这一类要求。<button type="button" className="btn-secondary btn-compact ml-2" onClick={() => changeFilter("all")}>查看全部要求</button></p>}
      </nav>
    </div>
    {overview}
    <div className="report-requirement-main min-w-0">
      {items.map((item, index) => <div key={item.requirementId} hidden={selected !== item.requirementId}>{articles[index]}</div>)}
      {visible.length > 0 && nextGap && <aside className="report-next-requirement"><p className="text-sm font-medium text-amber-800">下一项待核对</p><h3 className="mt-1 text-xl font-semibold">{nextGap.requirementTitle}</h3><a href={`#requirement-${nextGap.requirementId}`} className="btn mt-3">核对 {nextGap.skill || "这项要求"} →</a></aside>}
    </div>
  </section>;
}
