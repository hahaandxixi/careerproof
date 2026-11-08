/** Retrying into a new task keeps the report-comparison context. */
export function retryTaskHref(currentId: string, acceptedId: string, compareTo?: string | null): string | null {
  if (acceptedId === currentId) return null;
  const query = compareTo ? `?compareTo=${encodeURIComponent(compareTo)}` : "";
  return `/tasks/${encodeURIComponent(acceptedId)}${query}`;
}
