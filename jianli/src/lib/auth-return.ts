// Navigation is an allowlist; APIs remain the authority for each saved resource.
export function safeReturnPath(raw: string | null | undefined): string | null {
  if (!raw || raw.length > 2048 || !raw.startsWith("/") || raw.startsWith("//") || /[\\\s\u0000-\u001f\u007f]/.test(raw)) return null;
  try {
    const url = new URL(raw, "https://careerproof.invalid");
    if (url.origin !== "https://careerproof.invalid" || /%|\\/.test(url.pathname)) return null;
    if (!/^\/(?:$|portfolio$|recommendations$|applications$|notifications$|jobs(?:\/(?:[a-zA-Z0-9-]+)(?:\/(?:applications|edit))?)?$|reports(?:\/[a-zA-Z0-9-]+)?$|growth(?:\/[a-zA-Z0-9-]+)?$|tasks\/[a-zA-Z0-9-]+$|materials\/(?:resume|project)\/[a-zA-Z0-9-]+$)/.test(url.pathname)) return null;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch { return null; }
}

export function authEntry(path: "/login" | "/register", returnTo: string | null | undefined): string {
  const target = safeReturnPath(returnTo);
  return target ? `${path}?next=${encodeURIComponent(target)}` : path;
}

export function roleReturnPath(raw: string | null | undefined, role: string): string {
  const target = safeReturnPath(raw);
  const fallback = role === "student" ? "/portfolio" : role === "enterprise" ? "/jobs/mine" : "/jobs";
  if (!target) return fallback;
  const path = new URL(target, "https://careerproof.invalid").pathname;
  const enterpriseOnly = /^\/jobs\/(new|mine|manage)$|^\/jobs\/[^/]+\/(applications|edit)$/.test(path);
  const studentOnly = /^\/(portfolio|recommendations|applications|growth|reports|tasks)(\/|$)|^\/materials\//.test(path);
  if ((enterpriseOnly && role === "student") || (studentOnly && role === "enterprise")) return fallback;
  return target;
}

export interface ReturnChecks {
  getJob(id: string): Promise<unknown>;
  getReport(id: string): Promise<unknown>;
  growthTask(id: string): Promise<unknown>;
  getAnalysisTask(id: string): Promise<unknown>;
  jobApplications(id: string, page: number, pageSize: number): Promise<unknown>;
  previewResume(id: string): Promise<unknown>;
  listProjectFiles(id: string): Promise<unknown>;
}

export async function checkedReturnPath(raw: string | null | undefined, role: string, api: ReturnChecks): Promise<string> {
  const target = roleReturnPath(raw, role);
  const parts = new URL(target, "https://careerproof.invalid").pathname.split("/").filter(Boolean);
  try {
    if (parts[0] === "jobs" && parts[2] === "edit" && role === "admin") await api.getJob(parts[1]);
    else if (parts[0] === "jobs" && ["applications", "edit"].includes(parts[2])) await api.jobApplications(parts[1], 1, 1);
    else if (parts[0] === "jobs" && parts[1] && !["new", "mine", "manage"].includes(parts[1])) await api.getJob(parts[1]);
    else if (parts[0] === "reports" && parts[1]) await api.getReport(parts[1]);
    else if (parts[0] === "growth" && parts[1]) await api.growthTask(parts[1]);
    else if (parts[0] === "tasks" && parts[1]) await api.getAnalysisTask(parts[1]);
    else if (parts[0] === "materials" && parts[1] === "resume") await api.previewResume(parts[2]);
    else if (parts[0] === "materials" && parts[1] === "project") await api.listProjectFiles(parts[2]);
    return target;
  } catch (error) {
    const status = typeof error === "object" && error !== null && "status" in error ? error.status : null;
    if (status === 403 || status === 404) return roleReturnPath(null, role);
    // A network failure is not evidence of denied access. The destination keeps its retry UI.
    return target;
  }
}

/** Preserve the original task even when users switch auth pages through the header. */
export function authReturnFromLocation(pathname: string, search: string, hash = ""): string | null {
  return safeReturnPath(pathname === "/login" || pathname === "/register"
    ? new URLSearchParams(search).get("next")
    : pathname + search + hash);
}
