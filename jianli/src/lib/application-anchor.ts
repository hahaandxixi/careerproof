// B-15: application anchor reveal must happen once per explicit navigation.
// A lingering `#application-<uuid>` hash must not re-scroll on later list refreshes.

export type ApplicationAnchorOutcome =
  // No pending navigation: nothing to do and nothing to report.
  "idle"
  // The target scrolled into view once; this navigation is consumed.
  | "revealed"
  // The list has not loaded the target yet (or a repaint is still pending).
  | "waiting"
  // The target is loaded but excluded by the active filters; the page should
  // offer an actionable notice or restore a view that contains the target.
  | "filtered-out";

export interface ApplicationAnchorTarget {
  scrollIntoView(options: { block: "center" }): void;
}

export interface ApplicationAnchorRevealer {
  attempt(itemIds: readonly string[], visibleIds: readonly string[]): ApplicationAnchorOutcome;
  // User chose to keep the filtered view: consume the pending navigation so it
  // never scrolls later without a fresh hash change.
  dismiss(): void;
}

export function createApplicationAnchorRevealer(deps: {
  parseAnchorId: (hash: string) => string | null;
  readHash?: () => string;
  findTarget?: (id: string) => ApplicationAnchorTarget | null;
}): ApplicationAnchorRevealer {
  const readHash = deps.readHash ?? (() => (typeof location === "undefined" ? "" : location.hash));
  const findTarget = deps.findTarget ?? ((id) =>
    (typeof document === "undefined" ? null : document.getElementById(`application-${id}`)));
  // null means "hash never observed yet", so the first attempt after mount arms
  // the initial navigation just like a hashchange would.
  let lastHash: string | null = null;
  let pendingId: string | null = null;
  return {
    attempt(itemIds, visibleIds) {
      const hash = readHash();
      if (hash !== lastHash) {
        lastHash = hash;
        pendingId = deps.parseAnchorId(hash);
      }
      const id = pendingId;
      if (!id) return "idle";
      // The authorized list and its current filter decide whether a target is
      // eligible. A DOM node left over from an earlier render must not win.
      if (!itemIds.includes(id)) return "waiting";
      if (!visibleIds.includes(id)) return "filtered-out";
      const target = findTarget(id);
      if (!target) return "waiting";
      pendingId = null;
      target.scrollIntoView({ block: "center" });
      return "revealed";
    },
    dismiss() { pendingId = null; },
  };
}
