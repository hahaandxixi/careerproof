export function matchTaskHref(taskId: string, compareTo?: string | null, requirementId?: string | null) {
  const params = new URLSearchParams();
  if (compareTo) params.set("compareTo", compareTo);
  if (compareTo && requirementId) params.set("sourceRequirement", requirementId);
  return `/tasks/${encodeURIComponent(taskId)}${params.size ? `?${params}` : ""}`;
}

/** Retrying into a new task keeps the report-comparison context. */
export function retryTaskHref(currentId: string, acceptedId: string, compareTo?: string | null, requirementId?: string | null) {
  return acceptedId === currentId ? null : matchTaskHref(acceptedId, compareTo, requirementId);
}
