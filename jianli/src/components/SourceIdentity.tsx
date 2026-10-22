import type { ReportEvidence } from "@/lib/api/domain";
import { sourceLabel, type SourceMaterial } from "@/lib/source-label";

type Source = Pick<ReportEvidence, "filePath" | "projectVersionId">;

export default function SourceIdentity({ source, materials = [] }: {
  source: Source; materials?: readonly SourceMaterial[];
}) {
  return <span className="break-all">{sourceLabel(source, materials)}</span>;
}

export function SourceIdentityDetails({ source }: {
  source: Pick<ReportEvidence, "filePath" | "projectVersionId" | "lineStart" | "lineEnd" | "citationId" | "contentHash" | "evidenceType">;
}) {
  return <details className="mt-3 text-xs leading-6 text-slate-600">
    <summary className="cursor-pointer">完整来源与校验信息</summary>
    <p className="mt-2 break-all">保存路径：{source.filePath}<br />
      材料版本ID：{source.projectVersionId || "历史版本未记录，保留原始路径"}<br />
      原文范围：第 {source.lineStart}–{source.lineEnd} 行<br />
      引用编号：{source.citationId || "规则层来源，无模型引用编号"}<br />
      证据类型：{source.evidenceType}<br />内容摘要：{source.contentHash || "历史未记录"}</p>
  </details>;
}
