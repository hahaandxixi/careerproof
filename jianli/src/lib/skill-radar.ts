import type { ApplicationView } from "./api/client";
import type { ReportItem } from "./api/domain";
import { VERDICT_LABELS } from "./verdict-display.js";

export type RadarDimension = ApplicationView["dimensions"][number];
export const RADAR_STATUS = VERDICT_LABELS;
export function radarScore(d: RadarDimension): number | null {
  return d.verdict !== "unsupported" && RADAR_STATUS[d.verdict] &&
    typeof d.score === "number" && Number.isFinite(d.score) && d.score >= 0 && d.score <= 100 ? d.score : null;
}
export function radarPointKind(d: RadarDimension): "backed" | "claimed" | "none" {
  if (radarScore(d) === null) return "none";
  if (["supported", "verified", "partial"].includes(d.verdict)) return "backed";
  return d.verdict === "claimed_only" ? "claimed" : "none";
}
export function radarSelection(dimensions: RadarDimension[], id: string, items: ReportItem[] = []) {
  const dimension = dimensions.find(d => d.requirementId === id) ?? dimensions[0];
  const item = dimension ? items.find(i => i.requirementId === dimension.requirementId) : undefined;
  return { dimension, item };
}
export function radarSegments(dimensions: RadarDimension[]): [number, number][] {
  if (dimensions.length < 3) return [];
  return dimensions.flatMap((d, i) => {
    const next = (i + 1) % dimensions.length;
    return radarPointKind(d) === "backed" && radarPointKind(dimensions[next]) === "backed" ? [[i, next] as [number, number]] : [];
  });
}
