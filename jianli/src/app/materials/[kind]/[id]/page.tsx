import { notFound } from "next/navigation";
import AccessGate from "@/components/AccessGate";
import { materialReportReturn } from "@/lib/material-report-link";
import MaterialPreview from "@/components/MaterialPreview";
export default async function MaterialPage({ params, searchParams }: { params: Promise<{ id: string; kind: string }>; searchParams: Promise<{ fileId?: string; lineStart?: string; lineEnd?: string; reportId?: string; requirementId?: string; sourceId?: string }> }) {
  const { id, kind } = await params;
  const source = await searchParams;
  if (kind !== "resume" && kind !== "project") notFound();
  return <AccessGate roles={["student"]}><MaterialPreview id={id} kind={kind} reportReturnHref={materialReportReturn(source)} initialFileId={source.fileId} initialLineStart={Number(source.lineStart)} initialLineEnd={Number(source.lineEnd)} /></AccessGate>;
}
