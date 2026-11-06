"use client";

import type { ReactNode } from "react";
import { navigateEvidenceFragment, revealEvidenceAnchor } from "@/lib/evidence-anchor";

type Target = { citationId: string; targetId?: never } | { targetId: string; citationId?: never };
export default function EvidenceLink({ citationId, targetId, children, className }: Target & { children: ReactNode; className?: string }) {
  const anchor = targetId ?? `citation-${citationId}`;
  return <a href={`#${anchor}`} className={className} onClick={event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const target = revealEvidenceAnchor(anchor);
    navigateEvidenceFragment(`#${anchor}`);
    target?.scrollIntoView({ block: "start" });
    if (target) { target.tabIndex = -1; target.focus({ preventScroll: true }); }
  }}>{children}</a>;
}
