import { notFound } from "next/navigation";
import AccessGate from "@/components/AccessGate";
import { materialReportReturn } from "@/lib/material-report-link";
import MaterialPreview from "@/components/MaterialPreview";
import LegacyResumeRedirect from "@/components/LegacyResumeRedirect";
export default async function MaterialPage({ params, searchParams }: { params: Promise<{ id: string; kind: string }>; searchParams: Promise<{ fileId?: string; lineStart?: string; lineEnd?: string; reportId?: string; requirementId?: string; sourceId?: string; filter?: string; from?: string }> }) {
  const { id, kind } = await params;
  const source = await searchParams;
  if (kind !== "resume" && kind !== "project") notFound();
  const reportReturnHref = materialReportReturn(source);
  return <AccessGate roles={["student"]}>{kind === "resume"
    ? <LegacyResumeRedirect destination={reportReturnHref ?? "/portfolio"} />
    : <MaterialPreview id={id} reportReturnHref={reportReturnHref} initialFileId={source.fileId} initialLineStart={Number(source.lineStart)} initialLineEnd={Number(source.lineEnd)} />
  }</AccessGate>;
}
