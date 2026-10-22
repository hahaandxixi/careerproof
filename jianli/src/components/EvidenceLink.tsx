"use client";

import type { ReactNode } from "react";
import { revealEvidenceAnchor } from "@/lib/evidence-anchor";

type Target = { citationId: string; targetId?: never } | { targetId: string; citationId?: never };
export default function EvidenceLink({ citationId, targetId, children, className }: Target & { children: ReactNode; className?: string }) {
  const anchor = targetId ?? `citation-${citationId}`;
  return <a href={`#${anchor}`} className={className} onClick={event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const target = revealEvidenceAnchor(anchor);
    // Native hash navigation still updates the address, including keyboard activation.
    target?.scrollIntoView({ block: "start" });
  }}>{children}</a>;
}
