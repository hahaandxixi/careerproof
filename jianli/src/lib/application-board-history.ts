export interface ApplicationBoardFilters {
  q: string;
  status: string;
  requirementId: string;
  verdict: string;
}

export interface ApplicationBoardNavigation {
  page: number;
  filters: ApplicationBoardFilters;
  comparisonIds: string[];
}

const key = "careerproofApplicationBoard";
const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const text = (value: unknown, max: number) => typeof value === "string" ? value.slice(0, max) : "";

// Only navigation metadata belongs in the browser history entry. Report bodies,
// names, source code and reply drafts remain in the existing mounted session.
export function readApplicationBoardHistory(historyState: unknown, ownerId: string, jobId: string): ApplicationBoardNavigation {
  const saved = record(record(historyState)[key]);
  const valid = saved.version === 1 && saved.ownerId === ownerId && saved.jobId === jobId && !!ownerId;
  const filters = valid ? record(saved.filters) : {};
  return {
    page: valid && Number.isSafeInteger(saved.page) && (saved.page as number) > 0 ? saved.page as number : 1,
    filters: {
      q: text(filters.q, 200),
      status: ["submitted", "viewed", "downloaded", "replied"].includes(String(filters.status)) ? String(filters.status) : "",
      requirementId: text(filters.requirementId, 100),
      verdict: ["supported", "claimed_only", "gap", "unsupported"].includes(String(filters.verdict)) ? String(filters.verdict) : "",
    },
    comparisonIds: valid && Array.isArray(saved.comparisonIds)
      ? [...new Set(saved.comparisonIds.filter((id): id is string => typeof id === "string" && !!id && id.length <= 100))].slice(0, 4) : [],
  };
}

export function applicationBoardHistoryState(previous: unknown, ownerId: string, jobId: string, navigation: ApplicationBoardNavigation) {
  const saved = { version: 1, ownerId, jobId, ...navigation };
  return { ...record(previous), [key]: { version: 1, ownerId, jobId,
    ...readApplicationBoardHistory({ [key]: saved }, ownerId, jobId) } };
}
