"use client";

import Link from "next/link";
import ProjectFileReader from "./ProjectFileReader";
import VisualEvidencePanel from "./VisualEvidencePanel";

export default function MaterialPreview({ id, initialFileId, initialLineStart, initialLineEnd, reportReturnHref }: { id: string; initialFileId?: string; initialLineStart?: number; initialLineEnd?: number; reportReturnHref?: string }) {
  return <div className="space-y-6">
    <nav aria-label="返回">
      <Link href={reportReturnHref ?? "/portfolio"} className="btn-secondary btn-compact">← {reportReturnHref?.startsWith("/portfolio?") ? "返回材料列表" : reportReturnHref?.startsWith("/recommendations") ? "返回推荐依据" : reportReturnHref?.includes("#report-materials") ? "返回报告材料" : reportReturnHref ? "返回报告 · 这项要求" : "前往我的材料"}</Link>
    </nav>
    <div><h1 className="text-2xl font-bold">项目 / 作品文本预览</h1></div>
    <ProjectFileReader key={id} id={id} initialFileId={initialFileId} initialLineStart={initialLineStart}
      initialLineEnd={initialLineEnd} beforeFiles={<VisualEvidencePanel versionId={id} />} />
  </div>;
}
