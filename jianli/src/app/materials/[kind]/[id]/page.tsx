import { notFound } from "next/navigation";
import AccessGate from "@/components/AccessGate";
import { materialReportReturn } from "@/lib/material-report-link";
import MaterialPreview from "@/components/MaterialPreview";
import LegacyResumeRedirect from "@/components/LegacyResumeRedirect";
export default async function MaterialPage({ params, searchParams }: { params: Promise<{ id: string; kind: string }>; searchParams: Promise<{ fileId?: string; lineStart?: string; lineEnd?: string; reportId?: string; requirementId?: string; sourceId?: string; filter?: string; from?: string; materialType?: string; materialPage?: string; materialSearch?: string; materialVersion?: string; planCitation?: string; planId?: string }> }) {
  const { id, kind } = await params;
  const source = await searchParams;
  if (kind !== "resume" && kind !== "project") notFound();
  const reportReturnHref = materialReportReturn(source);
  const portfolioReturn = source.from === "portfolio" ? `/portfolio?${new URLSearchParams({
    materialType: source.materialType ?? "all", materialPage: source.materialPage ?? "1",
    materialSearch: source.materialSearch ?? "", materialVersion: id,
  })}` : undefined;
  const recommendationReturn = source.from === "recommendations"
    ? source.planId && source.planCitation
      ? `/recommendations?returnPlan=${encodeURIComponent(source.planId)}#plan-citation-${encodeURIComponent(source.planCitation)}`
      : "/recommendations" : undefined;
  return <AccessGate roles={["student"]}>{kind === "resume"
    ? <LegacyResumeRedirect destination={reportReturnHref ?? "/portfolio"} />
    : <MaterialPreview id={id} reportReturnHref={reportReturnHref ?? portfolioReturn ?? recommendationReturn} initialFileId={source.fileId} initialLineStart={Number(source.lineStart)} initialLineEnd={Number(source.lineEnd)} />
  }</AccessGate>;
}
