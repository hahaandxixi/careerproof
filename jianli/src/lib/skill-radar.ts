import type { ApplicationView } from "./api/client";
import type { ReportItem } from "./api/domain";
import { VERDICT_LABELS } from "./verdict-display.js";
import { resolveSupportScale, supportMeasure, type SupportScale } from "./support-index.js";

export type RadarDimension = ApplicationView["dimensions"][number];
export const RADAR_STATUS = VERDICT_LABELS;
/** Keep selection keyed by requirementId, even when skills or titles repeat. */
export function radarRequirementLabels(dimensions: readonly RadarDimension[]) {
  const primary = dimensions.map(dimension => dimension.skill?.trim() || dimension.title.trim());
  const counts = new Map<string, number>();
  for (const name of primary) counts.set(name.toLowerCase(), (counts.get(name.toLowerCase()) ?? 0) + 1);
  return new Map(dimensions.map((dimension, index) => {
    const name = primary[index];
    const duplicate = (counts.get(name.toLowerCase()) ?? 0) > 1;
    const number = `要求 ${index + 1}`;
    const title = dimension.title.trim() || name;
    const label = duplicate ? `${number} · ${title}` : name || number;
    // Existing SVG tiles hold at most eight glyphs on a dense chart.
    const shortTitle = duplicate ? `${index + 1}·${title}` : label;
    const chart = dimensions.length > 6 || Array.from(shortTitle).length > 8 ? number : shortTitle;
    return [dimension.requirementId, { label, chart }] as const;
  }));
}

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
