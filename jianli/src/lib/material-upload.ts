export type MaterialKind = "resume" | "project";
export type UploadedMaterial = { kind: MaterialKind; versionId: string };

// Match portfolio.py's suffix allowlists and byte limits. Browser MIME is
// descriptive only; the server still validates and parses the actual file.
const DOCUMENT_EXTENSIONS = ["pdf", "docx", "txt", "png", "jpg", "jpeg", "webp", "bmp"] as const;
export const MATERIAL_ACCEPT = {
  resume: DOCUMENT_EXTENSIONS.map(value => `.${value}`).join(","),
  project: ["zip", ...DOCUMENT_EXTENSIONS].map(value => `.${value}`).join(","),
};
export const MATERIAL_CONSTRAINTS = {
  resume: "PDF、DOCX、TXT、PNG、JPG/JPEG、WEBP、BMP；单文件不超过 10MB。",
  project: "ZIP 不超过 30MB；PDF、DOCX、TXT、PNG、JPG/JPEG、WEBP、BMP 不超过 10MB。",
};

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
}

export function materialFileError(kind: MaterialKind, file: Pick<File, "name" | "size">): string {
  const extension = extensionOf(file.name);
  if (!(DOCUMENT_EXTENSIONS as readonly string[]).includes(extension) && !(kind === "project" && extension === "zip")) {
    return `文件格式不支持。${MATERIAL_CONSTRAINTS[kind]}`;
  }
  const maxMiB = kind === "project" && extension === "zip" ? 30 : 10;
  return file.size > maxMiB * 1024 * 1024 ? `文件超过 ${maxMiB}MB，请压缩或选择其他文件。` : "";
}

export function pickMaterialFile(kind: MaterialKind, files: readonly File[]): { file: File | null; error: string } {
  if (files.length !== 1) return { file: null, error: files.length ? "每次请选择一个文件；多个项目可分别上传。" : "" };
  const error = materialFileError(kind, files[0]);
  return { file: error ? null : files[0], error };
}

export function materialFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function materialFileType(file: Pick<File, "name" | "type">): string {
  return file.type || `${extensionOf(file.name).toUpperCase() || "未知格式"}（浏览器未提供 MIME）`;
}

export function latestMaterialVersions<T extends { kind: MaterialKind; resourceId: string; versionNumber: number }>(versions: readonly T[]): T[] {
  const latest = new Map<string, T>();
  for (const version of versions) {
    const key = `${version.kind}:${version.resourceId}`;
    if (!latest.has(key) || version.versionNumber > latest.get(key)!.versionNumber) latest.set(key, version);
  }
  return [...latest.values()];
}

export function materialSelectionChanged(saved: readonly { kind: string; id: string }[], resumeId: string, projectIds: readonly string[]): boolean {
  const prior = new Set(saved.map(value => `${value.kind}:${value.id}`));
  const proposed = new Set([...(resumeId ? [`resume:${resumeId}`] : []), ...projectIds.map(id => `project:${id}`)]);
  return prior.size !== proposed.size || [...prior].some(value => !proposed.has(value));
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function uploadedMaterialFromQuery(query: Pick<URLSearchParams, "get">): UploadedMaterial | null {
  const kind = query.get("uploadedKind");
  const versionId = query.get("uploadedVersion");
  return (kind === "resume" || kind === "project") && versionId && UUID.test(versionId) ? { kind, versionId } : null;
}

export function growthUploadReturnHref(taskId: string, uploaded?: UploadedMaterial | null): string {
  const query = uploaded ? `?${new URLSearchParams({ uploadedKind: uploaded.kind, uploadedVersion: uploaded.versionId })}` : "";
  return `/growth/${taskId}${query}`;
}

// Missing/invalid historic timestamps stay absent instead of implying now.
export function materialVersionTime(createdAt?: string | null): string | null {
  if (!createdAt) return null;
  const date = new Date(createdAt);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
