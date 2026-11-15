import { notFound } from "next/navigation";
import AccessGate from "@/components/AccessGate";
import { materialReportReturn } from "@/lib/material-report-link";
import { normalizeJobsContext } from "@/lib/job-discovery";
import MaterialPreview from "@/components/MaterialPreview";
import LegacyResumeRedirect from "@/components/LegacyResumeRedirect";
export default async function MaterialPage({ params, searchParams }: { params: Promise<{ id: string; kind: string }>; searchParams: Promise<{ fileId?: string; lineStart?: string; lineEnd?: string; reportId?: string; requirementId?: string; sourceId?: string; filter?: string; from?: string; materialType?: string; materialPage?: string; materialSearch?: string; materialVersion?: string; planCitation?: string; planId?: string; jobsContext?: string | string[] }> }) {
  const { id, kind } = await params;
  const source = await searchParams;
  if (kind !== "resume" && kind !== "project") notFound();
  const reportReturnHref = materialReportReturn(source);
  const portfolioReturn = source.from === "portfolio" ? `/portfolio?${new URLSearchParams({
    materialType: source.materialType ?? "all", materialPage: source.materialPage ?? "1",
    materialSearch: source.materialSearch ?? "", materialVersion: id,
  })}` : undefined;
  let recommendationReturn: string | undefined;
  if (source.from === "recommendations") {
    const params = new URLSearchParams();
    const jobsContext = normalizeJobsContext(source.jobsContext);
    if (jobsContext) params.set("jobsContext", jobsContext);
    let hash = "";
    if (source.planId && source.planCitation) {
      params.set("returnPlan", source.planId);
      hash = `#plan-citation-${encodeURIComponent(source.planCitation)}`;
    }
    recommendationReturn = `/recommendations${params.size ? `?${params}` : ""}${hash}`;
  }
  return <AccessGate roles={["student"]}>{kind === "resume"
    ? <LegacyResumeRedirect destination={reportReturnHref ?? "/portfolio"} />
    : <MaterialPreview id={id} reportReturnHref={reportReturnHref ?? portfolioReturn ?? recommendationReturn} initialFileId={source.fileId} initialLineStart={Number(source.lineStart)} initialLineEnd={Number(source.lineEnd)} />
  }</AccessGate>;
}
