/** Resolve labels only against this report's frozen material list. */
export interface SourceMaterial {
  kind: string; id: string; title: string; versionNumber: number;
}
export interface SourceLocation {
  filePath: string; projectVersionId?: string | null;
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
