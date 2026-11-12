import { displayMaterialTitle } from "./demo-display-identity.js";

/** Resolve labels only against this report's frozen material list. */
export interface SourceMaterial {
  kind: string; id: string; title: string; versionNumber: number;
}
export function materialPathReadingText(text: string, materials: readonly SourceMaterial[]): string {
  return materials.filter(material => material.kind === "project").reduce(
    (value, material) => value.replaceAll(`${material.id}/`, ""), text,
  );
}

export interface SourceLocation {
  filePath: string; projectVersionId?: string | null;
}

export function sourceRelativePath(source: SourceLocation): string {
  if (!source.projectVersionId) return source.filePath;
  const prefix = source.projectVersionId;
  const boundary = source.filePath[prefix.length];
  return source.filePath.startsWith(prefix) && (boundary === "/" || boundary === "\\")
    ? source.filePath.slice(prefix.length + 1)
    : source.filePath;
}

/** Short identity for compact source labels and selectors. */
export function compactSourceLabel(source: SourceLocation, materials: readonly SourceMaterial[] = []) {
  const fileName = source.filePath.split(/[\\/]/).filter(Boolean).at(-1) || source.filePath;
  const material = materials.find(m => m.kind === "project" && m.id === source.projectVersionId);
  if (!material) return { fileName, material: "历史来源 · 版本未记录" };
  const peers = materials.filter(m => m.kind === "project" && m.title === material.title && m.versionNumber === material.versionNumber);
  const index = peers.findIndex(m => m.id === material.id);
  return { fileName, material: `${displayMaterialTitle(material.title, material.id) || "未命名项目"} · 第 ${material.versionNumber} 版${peers.length > 1 ? ` · 材料 ${index + 1}` : ""}` };
}

export function sourceLabel(source: SourceLocation, materials: readonly SourceMaterial[] = []): string {
  const material = materials.find(m => m.kind === "project" && m.id === source.projectVersionId);
  const relative = sourceRelativePath(source);
  return material ? `${compactSourceLabel(source, materials).material} · ${relative}` : relative;
}

/** UI-only anchors for rule candidates never acquire a model citation ID. */
export function sourceLocationId(requirementId: string, source: { citationId?: string | null }, index: number): string {
  return source.citationId ? `citation-${source.citationId}` : `rule-source-${requirementId}-${index + 1}`;
}
