/** Resolve labels only against this report's frozen material list. */
export interface SourceMaterial {
  kind: string; id: string; title: string; versionNumber: number;
}
export interface SourceLocation {
  filePath: string; projectVersionId?: string | null;
}

/** Short mobile identity; the untouched path and UUID remain in source details. */
export function compactSourceLabel(source: SourceLocation, materials: readonly SourceMaterial[] = []) {
  const fileName = source.filePath.split(/[\\/]/).filter(Boolean).at(-1) || source.filePath;
  const material = materials.find(m => m.kind === "project" && m.id === source.projectVersionId);
  if (!material) return { fileName, material: "历史来源 · 完整身份见详情" };
  const peers = materials.filter(m => m.kind === "project" && m.title === material.title && m.versionNumber === material.versionNumber);
  const index = peers.findIndex(m => m.id === material.id);
  return { fileName, material: `${material.title || "未命名项目"} · 第 ${material.versionNumber} 版${peers.length > 1 ? ` · 材料 ${index + 1}` : ""}` };
}

export function sourceLabel(source: SourceLocation, materials: readonly SourceMaterial[] = []): string {
  const material = materials.find(m => m.kind === "project" && m.id === source.projectVersionId);
  // A UUID-shaped filename is not proof of an internal material prefix.
  if (!material) return source.filePath;
  const prefix = `${material.id}/`;
  const relative = source.filePath.startsWith(prefix) ? source.filePath.slice(prefix.length) : source.filePath;
  const title = material.title || "未命名项目";
  const peers = materials.filter(m => m.kind === "project" && m.title === material.title && m.versionNumber === material.versionNumber);
  let identity = "";
  if (new Set(peers.map(m => m.id)).size > 1) {
    let length = 8;
    while (length < material.id.length && peers.some(m => m.id !== material.id && m.id.slice(0, length) === material.id.slice(0, length))) length += 4;
    identity = ` · 材料 ${material.id.slice(0, length)}`;
  }
  return `${title} · 第 ${material.versionNumber} 版${identity} · ${relative}`;
}

/** UI-only anchors for rule candidates never acquire a model citation ID. */
export function sourceLocationId(requirementId: string, source: { citationId?: string | null }, index: number): string {
  return source.citationId ? `citation-${source.citationId}` : `rule-source-${requirementId}-${index + 1}`;
}
