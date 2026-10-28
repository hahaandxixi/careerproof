import type { ApplicationView } from "./api/client";
import { unpackList, type ListPage, type PaginationInfo } from "./list-pagination.js";

export interface ApplicationBoardState {
  items: ApplicationView[];
  selected: ApplicationView | null;
  loading: boolean;
  error: string;
  notice: string;
  pagination?: PaginationInfo;
  comparison?: ApplicationView[];
  paused?: boolean;
}

export const initialApplicationBoardState: ApplicationBoardState = {
  items: [], selected: null, loading: true, error: "", notice: "",
};

interface Dependencies {
  list(): Promise<ApplicationView[] | ListPage<ApplicationView>>;
  open(id: string): Promise<ApplicationView>;
  detail?(id: string): Promise<ApplicationView>;
  download(id: string): Promise<{ blob: Blob; filename: string }>;
  reply(id: string, kind: string, text: string, references: ApplicationView["replyReferences"]): Promise<ApplicationView>;
  errorMessage(error: unknown): string;
}

export interface ApplicationBoardResume {
  authorizedIds: string[];
  selectedId: string | null;
}

// List membership must be rechecked before displaying an opened report. A late
// response from before refresh, tab hiding, or unmount must never restore it.
export function createApplicationBoardSession(
  api: Dependencies, publish: (state: ApplicationBoardState) => void,
) {
  let active = false;
  let generation = 0;
  let state = initialApplicationBoardState;
  let suspended = false;
  let retained: ApplicationView | null = null;
  let resumeWanted = false;
  let comparisonIds: string[] = [];
  let comparisonCache = new Map<string, ApplicationView>();
  let resuming: Promise<ApplicationBoardResume | null> | null = null;
  const set = (next: ApplicationBoardState) => {
    state = { ...next, paused: suspended, comparison: next.loading || suspended ? [] : comparisonIds.flatMap(id => comparisonCache.get(id) ?? []) };
    publish(state);
  };
  const current = (ticket: number) => active && ticket === generation;
  const matchingReport = (saved: ApplicationView, fresh: ApplicationView) => saved.jobId === fresh.jobId &&
    saved.reportId === fresh.reportId && saved.report?.id === fresh.reportId;
  async function recheckComparison(rows: ApplicationView[], ticket: number) {
    const verified = new Map<string, ApplicationView>();
    for (const id of comparisonIds) {
      try {
        const fresh = rows.find(item => item.id === id) ?? await api.detail?.(id);
        if (!current(ticket)) return;
        const saved = comparisonCache.get(id);
        if (!fresh || fresh.id !== id || fresh.status === "withdrawn" ||
            (saved && saved.jobId !== fresh.jobId) || (saved?.report && !matchingReport(saved, fresh))) continue;
        verified.set(id, { ...fresh, report: saved?.report });
      } catch { if (!current(ticket)) return; }
    }
    comparisonIds = comparisonIds.filter(id => verified.has(id));
    comparisonCache = verified;
  }

  async function run(
    operation: () => Promise<{ selected?: ApplicationView; deliver?: () => void; notice?: string }>,
    selectedId?: string,
    refreshSelectedMetadata = false,
  ) {
    if (!active || suspended) return false;
    retained = null;
    resumeWanted = false;
    const ticket = ++generation;
    set({ ...initialApplicationBoardState });
    try {
      const result = await operation();
      if (!current(ticket)) return false;
      if (result.selected && comparisonIds.includes(result.selected.id)) comparisonCache.set(result.selected.id, result.selected);
      const comparisonCount = comparisonIds.length;
      const list = unpackList(await api.list());
      const { items } = list;
      if (!current(ticket)) return false;
      await recheckComparison(items, ticket);
      if (!current(ticket)) return false;
      let authoritative = items.find(item => item.id === selectedId);
      let stillAuthorized = !selectedId || !!authoritative;
      // Filter/page absence is not revocation. Recheck the exact application
      // through the permissioned detail endpoint before retaining its snapshot.
      if (!stillAuthorized && selectedId && api.detail) {
        authoritative = await api.detail(selectedId);
        if (!current(ticket)) return false;
        if (authoritative.id !== selectedId) throw new Error("投递授权核对结果不一致");
        stillAuthorized = true;
      }
      if (stillAuthorized) result.deliver?.();
      if (!current(ticket)) return false;
      set({
        ...list, selected: stillAuthorized
          ? refreshSelectedMetadata && result.selected && authoritative
            ? { ...authoritative, report: result.selected.report }
            : result.selected ?? null
          : null,
        loading: false, error: "",
        notice: stillAuthorized ? result.notice ?? (comparisonCount > comparisonIds.length ? "部分对照候选人已无法确认授权，已移出对照。" : "") : "该投递已不在当前列表，已清除打开的报告。请刷新或翻页重新核对授权。",
      });
      return stillAuthorized;
    } catch (error) {
      if (current(ticket)) {
        comparisonCache.clear(); comparisonIds = [];
        set({ items: [], selected: null, loading: false, error: api.errorMessage(error), notice: "" });
      }
      return false;
    }
  }

  function resume(ids: string[] = []): Promise<ApplicationBoardResume | null> {
    if (!active) return Promise.resolve(null);
    suspended = false;
    resumeWanted = true;
    comparisonIds = [...new Set(ids)].slice(0, 4);
    if (resuming) return resuming;
    resuming = (async () => {
      // A second hide invalidates the first authorization read. Share that
      // in-flight request, then make one fresh read for the latest visible state.
      while (active && resumeWanted) {
        const ticket = ++generation;
        retained ??= state.selected;
        const saved = retained;
        const requested = [...new Set([...comparisonIds, ...(saved ? [saved.id] : [])])];
        set({ ...initialApplicationBoardState });
        try {
          const list = unpackList(await api.list());
          if (!current(ticket)) continue;
          const rows = list.items.filter(item => item.status !== "withdrawn");
          const allowed = new Map(rows.map(item => [item.id, item]));
          const rejected = new Set<string>();
          for (const id of requested) {
            if (allowed.has(id)) continue;
            try {
              const item = await api.detail?.(id);
              if (!current(ticket)) break;
              if (!item || item.id !== id || item.status === "withdrawn") rejected.add(id);
              else { allowed.set(id, item); rows.push(item); }
            } catch {
              if (!current(ticket)) break;
              rejected.add(id); // Unconfirmed access is never sufficient for restore.
            }
          }
          if (!current(ticket)) continue;
          const authoritative = saved ? allowed.get(saved.id) : undefined;
          let selected: ApplicationView | null = null;
          if (saved && authoritative) {
            if (saved.report && authoritative.reportId === saved.reportId
                && saved.report.id === saved.reportId && authoritative.jobId === saved.jobId) {
              selected = { ...authoritative, report: saved.report };
            } else rejected.add(saved.id);
          }
          if (saved && !selected) rejected.add(saved.id);
          const authorizedIds = requested.filter(id => allowed.has(id) && !rejected.has(id));
          for (const id of comparisonIds) {
            const fresh = allowed.get(id), saved = comparisonCache.get(id);
            if (!fresh || rejected.has(id) || (saved && saved.jobId !== fresh.jobId) || (saved?.report && !matchingReport(saved, fresh))) {
              rejected.add(id); comparisonCache.delete(id);
            } else comparisonCache.set(id, { ...fresh, report: saved?.report });
          }
          comparisonIds = comparisonIds.filter(id => !rejected.has(id));
          resumeWanted = false;
          retained = null;
          set({ ...list, items: rows.filter(item => !rejected.has(item.id)), selected,
            loading: false, error: "",
            notice: rejected.size ? "部分投递已无法确认授权或固定报告，已清除对应的报告和选中状态。" : "",
          });
          return { authorizedIds: authorizedIds.filter(id => !rejected.has(id)), selectedId: selected?.id ?? null };
        } catch (error) {
          if (!current(ticket)) continue;
          resumeWanted = false;
          retained = null;
          comparisonCache.clear(); comparisonIds = [];
          set({ items: [], selected: null, loading: false, error: api.errorMessage(error),
            notice: "授权核对未完成，已清除报告与选中状态。请刷新重试。" });
          return { authorizedIds: [], selectedId: null };
        }
      }
      return null;
    })().finally(() => { resuming = null; });
    return resuming;
  }

  return {
    activate() { active = true; suspended = false; },
    suspend() {
      if (state.selected) retained = state.selected;
      suspended = true;
      resumeWanted = false;
      ++generation;
      if (active) set({ items: [], selected: null, loading: false, error: "", notice: "" });
    },
    resume,
    clear() {
      ++generation;
      retained = null; resumeWanted = false; suspended = false;
      comparisonCache.clear(); comparisonIds = [];
      if (active) set({ items: [], selected: null, loading: false, error: "", notice: "" });
    },
    dispose() { active = false; ++generation; retained = null; resumeWanted = false; comparisonCache.clear(); comparisonIds = []; },
    selectComparison(ids: string[]) {
      if (!active || suspended) return Promise.resolve(false);
      comparisonIds = [...new Set(ids)].slice(0, 4);
      for (const id of comparisonCache.keys()) if (!comparisonIds.includes(id)) comparisonCache.delete(id);
      const selected = state.selected;
      return run(async () => ({ selected: selected ?? undefined }), selected?.id, true);
    },
    openComparison(ids: string[]) {
      if (ids.length !== 2 || ids.some(id => !comparisonIds.includes(id))) return Promise.resolve(false);
      const selected = state.selected;
      return run(async () => {
        const ticket = generation;
        for (const id of ids) {
          if (comparisonCache.get(id)?.report) continue;
          const opened = await api.open(id);
          if (!current(ticket)) return {};
          if (opened.id !== id || opened.status === "withdrawn") throw new Error("投递授权核对结果不一致");
          comparisonCache.set(id, opened);
        }
        return { selected: selected ?? undefined };
      }, selected?.id, true);
    },
    refresh() { return run(async () => ({})); },
    filter() {
      const selected = state.selected;
      // Only the immutable report survives filtering. Status, reply, events and
      // other mutable fields come from the fresh authorized row/detail.
      return run(async () => ({ selected: selected ?? undefined }), selected?.id, true);
    },
    open(id: string) { return run(async () => ({ selected: await api.open(id) }), id); },
    download(deliver: (file: { blob: Blob; filename: string }) => void) {
      const id = state.selected?.id;
      if (!id || state.loading) return Promise.resolve(false);
      return run(async () => {
        const file = await api.download(id);
        const selected = await api.open(id);
        return {
          selected, deliver: () => deliver(file),
          notice: "已收到授权简历文件，已请求浏览器保存。请检查浏览器下载列表；本提示不证明文件已保存到磁盘。",
        };
      }, id);
    },
    reply(kind: string, text: string, references: ApplicationView["replyReferences"] = []) {
      const id = state.selected?.id;
      if (!id || state.loading) return Promise.resolve(false);
      return run(async () => {
        await api.reply(id, kind, text, references);
        return { selected: await api.open(id) };
      }, id);
    },
  };
}
