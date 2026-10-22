import type { ReportItem } from "./api/domain.ts";
import { evidenceWorkspace } from "./evidence-workspace";
import { sourceLocationId } from "./source-label";

/** Reading order follows the existing saved-evidence priority, never a new score. */
export function initialReportRequirement(items: ReportItem[]): string | null {
  return evidenceWorkspace(items).priorities[0]?.requirementId ?? items[0]?.requirementId ?? null;
}

export function reportAnchorId(hash: string): string | null {
  if (!hash.startsWith("#") || hash.length < 2) return null;
  try { return decodeURIComponent(hash.slice(1)); } catch { return null; }
}

/** Match saved identities exactly; citation IDs need not encode a requirement index. */
export function requirementForReportAnchor(items: ReportItem[], anchor: string | null): string | null {
  if (!anchor) return null;
  return items.find(item =>
    anchor === `requirement-${item.requirementId}` || anchor === `growth-${item.requirementId}` ||
    item.evidenceList.some((source, index) => anchor === sourceLocationId(item.requirementId, source, index))
  )?.requirementId ?? null;
}

export function reportEntryRequirement(items: ReportItem[], hash: string, search = ""): string | null {
  const linked = requirementForReportAnchor(items, reportAnchorId(hash));
  if (linked) return linked;
  const reply = new URLSearchParams(search).get("enterpriseReply");
  return items.some(item => item.requirementId === reply) ? reply : null;
}
