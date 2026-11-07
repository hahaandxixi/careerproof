/** Preserve opaque App Router history state; native hash entries have null state. */
export function navigateEvidenceFragment(
  hash: string, view: Pick<Window, "location" | "history" | "dispatchEvent"> = window,
) {
  if (!hash.startsWith("#")) throw new Error("Evidence navigation requires a local fragment.");
  if (view.location.hash === hash) return;
  view.history.pushState(view.history.state, "", hash);
  // pushState does not emit hashchange; existing report/flow listeners still own
  // selection, disclosure, focus and anchor restoration, without route/data delays.
  view.dispatchEvent(new Event("hashchange"));
}

/** Expand every closed evidence container before scrolling or fragment navigation. */
export function revealEvidenceAnchor(id: string, documentRoot: Pick<Document, "getElementById"> = document): HTMLElement | null {
  const target = documentRoot.getElementById(id);
  // Report sections must be revealed before disclosures, scrolling and focus.
  if (target && typeof window !== "undefined") window.dispatchEvent(new CustomEvent("careerproof:reveal-evidence", { detail: target }));
  for (let parent = target?.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === "DETAILS") (parent as HTMLDetailsElement).open = true;
  }
  return target;
}
