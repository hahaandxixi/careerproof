type ReportListState = { q: string; jobId: string; page: number; includeHistory: boolean; candidateId?: string };

export function readReportListState(params: Pick<URLSearchParams, "get">): ReportListState {
  const jobId = params.get("jobId") ?? "";
  const page = Number(params.get("page"));
  const candidateId = params.get("candidateId");
  return {
    q: (params.get("q") ?? "").trim().slice(0, 200),
    jobId: /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(jobId) ? jobId : "",
    ...(candidateId && /^[\w-]{1,200}$/.test(candidateId) ? { candidateId } : {}),
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    includeHistory: params.get("history") === "1",
  };
}

export function reportListQuery(state: ReportListState) {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.jobId) {
    params.set("jobId", state.jobId);
    if (state.candidateId) params.set("candidateId", state.candidateId);
  }
  if (state.page > 1) params.set("page", String(state.page));
  if (state.includeHistory) params.set("history", "1");
  return params;
}

export function reportListHref(state: ReportListState) {
  const query = reportListQuery(state).toString();
  return query ? `/reports?${query}` : "/reports";
}

export function reportOrigin(value?: string | null) {
  return readReportListState(new URLSearchParams(value ?? ""));
}

export function reportVersionHref(id: string, origin?: string | null, hash = "") {
  const query = reportListQuery(reportOrigin(origin)).toString();
  return `/reports/${id}${query ? "?" + new URLSearchParams({ from: query }) : ""}${hash}`;
}
