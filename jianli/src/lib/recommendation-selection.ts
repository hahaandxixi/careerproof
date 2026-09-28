export function jobAnalysisHref(
  jobId: string,
  resumeVersionId: string,
  projectVersionIds: string[],
) {
  const query = new URLSearchParams({ resumeVersionId });
  projectVersionIds.slice(0, 10).forEach(id => query.append("projectVersionId", id));
  return `/jobs/${encodeURIComponent(jobId)}?${query.toString()}`;
}

export function resolveInitialMaterialSelection(
  completedResumeIds: string[],
  completedProjectIds: string[],
  requestedResumeId: string,
  requestedProjectIds: string[],
) {
  const resumeIds = new Set(completedResumeIds);
  const projectIds = new Set(completedProjectIds);
  return {
    resumeVersionId: resumeIds.has(requestedResumeId)
      ? requestedResumeId
      : "",
    projectVersionIds: [...new Set(requestedProjectIds)]
      .filter(id => projectIds.has(id))
      .slice(0, 10),
  };
}
