import type { ApplicationView } from "./api/client";
import type { ReportItem } from "./api/domain";
import { VERDICT_LABELS } from "./verdict-display.js";
import { resolveSupportScale, supportMeasure, type SupportScale } from "./support-index.js";

export type RadarDimension = ApplicationView["dimensions"][number];
export const RADAR_STATUS = VERDICT_LABELS;
export function radarPosition(index: number, count: number, ratio: number) {
  const angle = index * 2 * Math.PI / count - 3 * Math.PI / 4;
  return { x: 200 + 108 * ratio * Math.cos(angle), y: 200 + 108 * ratio * Math.sin(angle) };
}
export function radarScore(d: RadarDimension, scale = resolveSupportScale([d])): number | null {
  return d.verdict !== "unsupported" && RADAR_STATUS[d.verdict] &&
    !supportMeasure(d, scale).issue && typeof d.score === "number" ? d.score : null;
}
export function radarPointKind(d: RadarDimension, scale?: SupportScale): "backed" | "claimed" | "none" {
  if (radarScore(d, scale) === null) return "none";
  if (["supported", "verified", "partial"].includes(d.verdict)) return "backed";
  return d.verdict === "claimed_only" ? "claimed" : "none";
}
export function radarSelection(dimensions: RadarDimension[], id: string, items: ReportItem[] = []) {
  const dimension = dimensions.find(d => d.requirementId === id) ?? dimensions[0];
  const item = dimension ? items.find(i => i.requirementId === dimension.requirementId) : undefined;
  return { dimension, item };
}
export function radarSegments(dimensions: RadarDimension[], scale = resolveSupportScale(dimensions)): [number, number][] {
  if (dimensions.length < 3) return [];
  return dimensions.flatMap((d, i) => {
    const next = (i + 1) % dimensions.length;
    return radarPointKind(d, scale) === "backed" && radarPointKind(dimensions[next], scale) === "backed" ? [[i, next] as [number, number]] : [];
  });
}
