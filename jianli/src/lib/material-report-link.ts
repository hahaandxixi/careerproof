import type { WorkspaceFilter } from "./report-workspace";

type ReportSourceContext = {
  reportId?: string;
  requirementId?: string;
  sourceId?: string;
  filter?: string;
  from?: string;
};

export function readWorkspaceFilter(value?: string | null): WorkspaceFilter | undefined {
  const filters: readonly WorkspaceFilter[] = ["priority", "all", "supported", "partial", "gaps", "other"];
  return filters.find(filter => filter === value);
}

export function materialReportContext(reportId: string, requirementId?: string, sourceId?: string, filter?: WorkspaceFilter, origin?: string) {
  const params = new URLSearchParams({ reportId });
  if (requirementId) params.set("requirementId", requirementId);
  if (sourceId) params.set("sourceId", sourceId);
  if (filter) params.set("filter", filter);
  if (origin) params.set("from", origin);
  return params;
}

export function materialReportReturn({ reportId, requirementId, sourceId, filter, from }: ReportSourceContext): string | undefined {
  const safeId = (value: unknown): value is string => typeof value === "string" && /^[\w-]{1,200}$/.test(value);
  if (!safeId(reportId)) return undefined;
  const fragment = safeId(requirementId)
    ? safeId(sourceId) && (sourceId.startsWith("citation-") || sourceId.startsWith(`rule-source-${requirementId}-`))
      ? sourceId : `requirement-${requirementId}`
    : "report-materials";
  const params = new URLSearchParams();
  const savedFilter = readWorkspaceFilter(filter);
  if (savedFilter) params.set("filter", savedFilter);
  // A 200-character search can be over 512 bytes after URL encoding.
  if (from) params.set("from", from.slice(0, 4096));
  return `/reports/${reportId}${params.size ? "?" + params : ""}#${fragment}`;
}
