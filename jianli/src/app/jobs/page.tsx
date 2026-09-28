import JobList from "@/components/JobList";
export default async function JobsPage({ searchParams }: { searchParams: Promise<{ q?: string | string[] }> }) {
  const query = (await searchParams).q;
  return <JobList initialQuery={typeof query === "string" ? query.slice(0, 200) : ""} />;
}
