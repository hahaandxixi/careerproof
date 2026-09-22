import JobDetailView from "@/components/JobDetailView";
export default async function JobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    resumeVersionId?: string | string[];
    projectVersionId?: string | string[];
  }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const initialResumeVersionId = Array.isArray(query.resumeVersionId)
    ? query.resumeVersionId[0] ?? ""
    : query.resumeVersionId ?? "";
  const initialProjectVersionIds = Array.isArray(query.projectVersionId)
    ? query.projectVersionId.slice(0, 10)
    : query.projectVersionId
      ? [query.projectVersionId]
      : [];
  return <JobDetailView id={id} initialResumeVersionId={initialResumeVersionId} initialProjectVersionIds={initialProjectVersionIds} />;
}
