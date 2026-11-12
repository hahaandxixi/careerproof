export function jobAnalysisHref(
  jobId: string,
  resumeVersionId: string,
  projectVersionIds: string[],
) {
  const query = new URLSearchParams({ resumeVersionId });
  projectVersionIds.slice(0, 10).forEach(id => query.append("projectVersionId", id));
  return `/jobs/${encodeURIComponent(jobId)}?${query.toString()}`;
}

export function careerPlanHref(resumeVersionId: string, projectVersionIds: string[]) {
  const query = new URLSearchParams({ resumeVersionId });
  projectVersionIds.slice(0, 10).forEach(id => query.append("projectVersionId", id));
  return `/recommendations?${query.toString()}`;
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

export function unavailableRequestedMaterials(
  selection: ReturnType<typeof resolveInitialMaterialSelection>,
  requestedResumeId: string,
  requestedProjectIds: string[],
) {
  const missing = [...new Set(requestedProjectIds)].filter(id => !selection.projectVersionIds.includes(id));
  return [
    ...(requestedResumeId && !selection.resumeVersionId ? ["简历版本"] : []),
    ...(missing.length ? [`${missing.length} 个项目版本`] : []),
  ];
}
