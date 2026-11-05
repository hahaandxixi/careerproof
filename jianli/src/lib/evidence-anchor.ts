/** Expand every closed evidence container before scrolling or native hash navigation. */
export function revealEvidenceAnchor(id: string, documentRoot: Pick<Document, "getElementById"> = document): HTMLElement | null {
  const target = documentRoot.getElementById(id);
  // Report sections must be revealed before disclosures, scrolling and focus.
  if (target && typeof window !== "undefined") window.dispatchEvent(new CustomEvent("careerproof:reveal-evidence", { detail: target }));
  for (let parent = target?.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === "DETAILS") (parent as HTMLDetailsElement).open = true;
  }
  return target;
}
