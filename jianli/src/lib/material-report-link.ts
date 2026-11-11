type ReportSourceContext = {
  reportId?: string;
  requirementId?: string;
  sourceId?: string;
};

export function materialReportContext(reportId: string, requirementId?: string, sourceId?: string) {
  const params = new URLSearchParams({ reportId });
  if (requirementId) params.set("requirementId", requirementId);
  if (sourceId) params.set("sourceId", sourceId);
  return params;
}

export function materialReportReturn({ reportId, requirementId, sourceId }: ReportSourceContext): string | undefined {
  const safeId = (value: unknown): value is string => typeof value === "string" && /^[\w-]{1,200}$/.test(value);
  if (!safeId(reportId)) return undefined;
  const fragment = safeId(requirementId)
    ? safeId(sourceId) && (sourceId.startsWith("citation-") || sourceId.startsWith(`rule-source-${requirementId}-`))
      ? sourceId : `requirement-${requirementId}`
    : "report-materials";
  return `/reports/${reportId}#${fragment}`;
}
