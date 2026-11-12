import type { ReactNode } from "react";
import type { ReportEvidence } from "@/lib/api/domain";
import { compactSourceLabel, sourceLabel, sourceRelativePath, type SourceMaterial } from "@/lib/source-label";

type Source = Pick<ReportEvidence, "filePath" | "projectVersionId">;

export default function SourceIdentity({ source, materials = [], compact = false }: {
  source: Source; materials?: readonly SourceMaterial[]; compact?: boolean;
}) {
  if (compact) {
    const label = compactSourceLabel(source, materials);
    return <span className="break-words"><span className="sm:hidden"><strong>{label.fileName}</strong><span className="mt-1 block font-normal text-slate-600">{label.material}</span></span><span className="hidden sm:inline">{sourceLabel(source, materials)}</span></span>;
  }
  return <span className="break-all">{sourceLabel(source, materials)}</span>;
}

export function SourceIdentityDetails({ source, children }: {
  source: Source; children?: ReactNode;
}) {
  const path = sourceRelativePath(source);
  const hasDirectories = /[/\\]/.test(path);
  if (!hasDirectories && !children) return null;
  return <details className="mt-3 text-xs leading-6 text-slate-600">
    <summary className="cursor-pointer">来源详情</summary>
    {hasDirectories && <p className="mt-2 break-all">文件路径：{path}</p>}
    {children}
  </details>;
}
