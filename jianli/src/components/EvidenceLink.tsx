"use client";

import type { ReactNode } from "react";
import { revealEvidenceAnchor } from "@/lib/evidence-anchor";

export default function EvidenceLink({ citationId, children, className }: { citationId: string; children: ReactNode; className?: string }) {
  const anchor = `citation-${citationId}`;
  return <a href={`#${anchor}`} className={className} onClick={event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const target = revealEvidenceAnchor(anchor);
    // Native hash navigation still updates the address, including keyboard activation.
    target?.scrollIntoView({ block: "start" });
  }}>{children}</a>;
}
