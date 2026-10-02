import AccessGate from "@/components/AccessGate";
import CareerRecommendations from "@/components/CareerRecommendations";

export default async function RecommendationsPage({ searchParams }: {
  searchParams: Promise<{ resumeVersionId?: string | string[]; projectVersionId?: string | string[] }>;
}) {
  const query = await searchParams;
  const resume = Array.isArray(query.resumeVersionId) ? query.resumeVersionId[0] ?? "" : query.resumeVersionId ?? "";
  const projects = Array.isArray(query.projectVersionId) ? query.projectVersionId.slice(0, 10)
    : query.projectVersionId ? [query.projectVersionId] : [];
  return <AccessGate roles={["student"]}><CareerRecommendations initialResumeVersionId={resume} initialProjectVersionIds={projects} /></AccessGate>;
}
