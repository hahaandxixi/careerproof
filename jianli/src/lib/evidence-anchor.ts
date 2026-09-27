/** Expand every closed evidence container before scrolling or native hash navigation. */
export function revealEvidenceAnchor(id: string, documentRoot: Pick<Document, "getElementById"> = document): HTMLElement | null {
  const target = documentRoot.getElementById(id);
  for (let parent = target?.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === "DETAILS") (parent as HTMLDetailsElement).open = true;
  }
  return target;
}
