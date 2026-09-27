"use client";

import { useEffect } from "react";
import { revealEvidenceAnchor } from "@/lib/evidence-anchor";

/** Render after the evidence nodes exist, including async report loading. */
export default function EvidenceAnchorRestore({ revision }: { revision?: string }) {
  useEffect(() => {
    const restore = () => {
      if (!window.location.hash) return;
      let anchor: string;
      try { anchor = decodeURIComponent(window.location.hash.slice(1)); } catch { return; }
      revealEvidenceAnchor(anchor)?.scrollIntoView({ block: "start" });
    };
    const frame = requestAnimationFrame(restore);
    window.addEventListener("hashchange", restore);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("hashchange", restore); };
  }, [revision]);
  return null;
}
