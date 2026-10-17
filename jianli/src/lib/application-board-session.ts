import type { ApplicationView } from "./api/client";
import { unpackList, type ListPage, type PaginationInfo } from "./list-pagination.js";

export interface ApplicationBoardState {
  items: ApplicationView[];
  selected: ApplicationView | null;
  loading: boolean;
  error: string;
  notice: string;
  pagination?: PaginationInfo;
}

export const initialApplicationBoardState: ApplicationBoardState = {
  items: [], selected: null, loading: true, error: "", notice: "",
};

interface Dependencies {
  list(): Promise<ApplicationView[] | ListPage<ApplicationView>>;
  open(id: string): Promise<ApplicationView>;
  download(id: string): Promise<{ blob: Blob; filename: string }>;
  reply(id: string, kind: string, text: string, references: ApplicationView["replyReferences"]): Promise<ApplicationView>;
  errorMessage(error: unknown): string;
}

// List membership must be rechecked before displaying an opened report. A late
// response from before refresh, tab hiding, or unmount must never restore it.
export function createApplicationBoardSession(
  api: Dependencies, publish: (state: ApplicationBoardState) => void,
) {
  let active = false;
  let generation = 0;
  let state = initialApplicationBoardState;
  const set = (next: ApplicationBoardState) => { state = next; publish(next); };
  const current = (ticket: number) => active && ticket === generation;

  async function run(
    operation: () => Promise<{ selected?: ApplicationView; deliver?: () => void; notice?: string }>,
    selectedId?: string,
  ) {
    if (!active) return false;
    const ticket = ++generation;
    set({ ...initialApplicationBoardState });
    try {
      const result = await operation();
      if (!current(ticket)) return false;
      const list = unpackList(await api.list());
      const { items } = list;
      if (!current(ticket)) return false;
      const stillAuthorized = !selectedId || items.some(item => item.id === selectedId);
      if (stillAuthorized) result.deliver?.();
      if (!current(ticket)) return false;
      set({
        ...list, selected: stillAuthorized ? result.selected ?? null : null,
        loading: false, error: "",
        notice: stillAuthorized ? result.notice ?? "" : "该投递已不在当前列表，已清除打开的报告。请刷新或翻页重新核对授权。",
      });
      return stillAuthorized;
    } catch (error) {
      if (current(ticket)) set({ items: [], selected: null, loading: false, error: api.errorMessage(error), notice: "" });
      return false;
    }
  }

  return {
    activate() { active = true; },
    clear() {
      ++generation;
      if (active) set({ items: [], selected: null, loading: false, error: "", notice: "" });
    },
    dispose() { active = false; ++generation; },
    refresh() { return run(async () => ({})); },
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
