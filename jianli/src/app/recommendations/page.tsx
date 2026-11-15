import Link from "next/link";
import AccessGate from "@/components/AccessGate";
import CareerRecommendations from "@/components/CareerRecommendations";
import { normalizeJobsContext, recommendationDiscoveryReturnHref } from "@/lib/job-discovery";

export default async function RecommendationsPage({ searchParams }: {
  searchParams: Promise<{ resumeVersionId?: string | string[]; projectVersionId?: string | string[]; jobsContext?: string | string[] }>;
}) {
  const query = await searchParams;
  const resume = Array.isArray(query.resumeVersionId) ? query.resumeVersionId[0] ?? "" : query.resumeVersionId ?? "";
  const projects = Array.isArray(query.projectVersionId) ? query.projectVersionId.slice(0, 10)
    : query.projectVersionId ? [query.projectVersionId] : [];
  const jobsContext = normalizeJobsContext(query.jobsContext);
  const returnHref = recommendationDiscoveryReturnHref(jobsContext);
  return <AccessGate roles={["student"]}>
    <Link className="review-back" href={returnHref} scroll={!returnHref.includes("#")}>← 返回岗位发现</Link>
    <CareerRecommendations initialResumeVersionId={resume} initialProjectVersionIds={projects} jobsContext={jobsContext} />
  </AccessGate>;
}
