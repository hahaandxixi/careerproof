import type { ApplicationView } from "./api/client";
export interface ApplicationListState {
  items: ApplicationView[]; loading: boolean; error: string;
}
export function createApplicationListSession(
  api: { list(): Promise<ApplicationView[]>; withdraw(id: string): Promise<unknown>; errorMessage(error: unknown): string },
  publish: (value: ApplicationListState) => void,
) {
  let active = false, generation = 0, withdrawing = false, refreshQueued = false;
  const current = (ticket: number) => active && generation === ticket;
  async function run(operation?: () => Promise<unknown>) {
    if (!active) return;
    const ticket = ++generation;
    publish({ items: [], loading: true, error: "" });
    try {
      if (operation) await operation();
      if (!current(ticket)) return;
      const items = await api.list();
      if (current(ticket)) publish({ items, loading: false, error: "" });
    } catch (error) {
      if (current(ticket)) publish({ items: [], loading: false, error: api.errorMessage(error) });
    }
  }
  return {
    activate() { active = true; },
    clear() { refreshQueued = false; ++generation; if (active) publish({ items: [], loading: false, error: "" }); },
    dispose() { refreshQueued = false; active = false; ++generation; },
    refresh() { if (withdrawing) { refreshQueued = true; return Promise.resolve(); } return run(); },
    async withdraw(id: string) {
      if (!active || withdrawing) return;
      withdrawing = true;
      try { await run(() => api.withdraw(id)); } finally {
        withdrawing = false;
        if (refreshQueued && active) { refreshQueued = false; await run(); }
      }
    },
  };
}
