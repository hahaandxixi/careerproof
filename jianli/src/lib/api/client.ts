import type { Page, JobOptions, Enterprise, JobSummary, JobDetail, JobInput, ResumePreview, ProjectFileSummary, ProjectFileContent, ReportSummary, MatchReport, DeepSeekWebHandoff } from "./domain";

const API_PREFIX = "/backend/api/v1";

export type UserRole = "student" | "enterprise" | "admin";
export type TaskStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T;
  requestId: string;
}

interface ValidationDetail {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
}

export interface CurrentUser {
  id: string;
  email: string;
  displayName: string;
  role: UserRole;
  isActive: boolean;
}

export interface AuthData {
  user: CurrentUser;
  accessTokenExpiresIn: number;
}

export interface ResumeUploadData {
  resumeId: string;
  versionId: string;
  taskId: string;
  status: TaskStatus;
}

export interface ProjectView {
  id: string;
  name: string;
  description: string;
  version: number;
}

export interface MaterialVersion {
  id: string;
  versionNumber: number;
  originalFilename: string | null;
  sizeBytes: number | null;
  createdAt: string;
  status: string;
  taskId: string | null;
  progress: number | null;
  currentStep: string | null;
  errorMessage: string | null;
}

export interface ResumeHistory {
  id: string;
  title: string;
  createdAt: string;
  versions: MaterialVersion[];
}

export interface ProjectHistory extends ProjectView {
  createdAt: string;
  versions: MaterialVersion[];
}

export interface ProjectVersionUploadData {
  projectId: string;
  versionId: string;
  taskId: string;
  status: TaskStatus;
}

export interface AgentStep {
  step: number;
  eventType: string;
  name: string;
  detail: string;
  payload: Record<string, unknown>;
}

export interface AnalysisTask {
  id: string;
  taskType: string;
  status: TaskStatus;
  progress: number;
  currentStep: string | null;
  errorMessage: string | null;
  totalCostRmb: string;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  reportId: string | null;
  steps: AgentStep[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: number;
  readonly requestId?: string;
  readonly details?: unknown;

  constructor(
    message: string,
    status: number,
    code?: number,
    requestId?: string,
    details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

async function readEnvelope<T>(response: Response): Promise<ApiEnvelope<T> | null> {
  try {
    return (await response.json()) as ApiEnvelope<T>;
  } catch {
    return null;
  }
}

let refreshInFlight: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_PREFIX}/auth/refresh`, {
      method: "POST", credentials: "include", cache: "no-store",
    }).then(async (response) => {
      if (response.status === 401) return false;
      if (!response.ok) {
        const envelope = await readEnvelope<unknown>(response);
        throw new ApiError(envelope?.message ?? "暂时无法恢复会话，请稍后重试。", response.status, envelope?.code, envelope?.requestId);
      }
      return true;
    }).catch((reason) => {
      if (reason instanceof ApiError) throw reason;
      throw new Error("无法连接服务以确认会话，请检查网络后重试。");
    }).finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  allowRefresh = true
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, { ...init, credentials: "include", cache: "no-store" });
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
    throw new Error("无法连接服务，请确认网络和后端运行状态后重试。");
  }

  if (response.status === 401 && allowRefresh && !path.startsWith("/auth/")) {
    if (await refreshSession()) return request<T>(path, init, false);
  }

  const envelope = await readEnvelope<T>(response);
  if (response.status === 401 && path !== "/users/me" && !path.startsWith("/auth/") && typeof window !== "undefined") {
    window.dispatchEvent(new Event("careerproof:session-expired"));
  }
  if (!response.ok || !envelope) {
    throw new ApiError(
      envelope?.message ?? `请求失败（HTTP ${response.status}）`,
      response.status,
      envelope?.code,
      envelope?.requestId,
      (envelope?.data as { details?: unknown } | undefined)?.details
    );
  }
  return envelope.data;
}

function jsonBody(value: unknown): Pick<RequestInit, "body" | "headers"> {
  return {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(value),
  };
}

export const api = {
  listJobs(filters: Record<string, string | number> = {}, mine = false) {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value !== "") query.set(key, String(value)); });
    return request<Page<JobSummary>>(`/jobs${mine ? "/mine" : ""}?${query}`);
  },
  jobOptions() { return request<JobOptions>("/jobs/options"); },
  getJob(id: string) { return request<JobDetail>(`/jobs/${id}`); },
  createJob(payload: JobInput) { return request<JobDetail>("/jobs", { method: "POST", ...jsonBody(payload) }); },
  updateJob(id: string, payload: Partial<Omit<JobInput, "enterpriseId" | "companyName">>) {
    return request<JobDetail>(`/jobs/${id}`, { method: "PATCH", ...jsonBody(payload) });
  },
  listEnterprises() { return request<Enterprise[]>("/enterprises/me"); },
  createEnterprise(payload: { name: string; description: string }) {
    return request<Enterprise>("/enterprises", { method: "POST", ...jsonBody(payload) });
  },
  createMatch(payload: { jobId: string; resumeVersionId: string; projectVersionIds: string[] }) {
    return request<{ taskId: string; status: TaskStatus }>("/matches", { method: "POST", ...jsonBody(payload) });
  },
  listReports(page = 1, pageSize = 20) { return request<ReportSummary[]>(`/match-reports?page=${page}&pageSize=${pageSize}`); },
  getReport(id: string) { return request<MatchReport>(`/match-reports/${id}`); },
  getDeepSeekWebHandoff(id: string) {
    return request<DeepSeekWebHandoff>(`/match-reports/${id}/deepseek-web`);
  },
  importDeepSeekWebAnalysis(id: string, response: Record<string, unknown>, contextDigest: string) {
    return request<MatchReport>(`/match-reports/${id}/deepseek-web`, {
      method: "POST", ...jsonBody({ response, contextDigest }),
    });
  },
  reviewEvidence(reportId: string, requirementId: string, status: "pending" | "accepted" | "rejected" | "corrected", note?: string) {
    return request<MatchReport["items"][number]>(`/match-reports/${reportId}/items/${requirementId}/review`, {
      method: "PATCH",
      ...jsonBody({ status, note: note || null }),
    });
  },
  retryTask(id: string) { return request<{ taskId: string; status: TaskStatus }>(`/analysis-tasks/${id}/retry`, { method: "POST" }); },
  previewResume(id: string) { return request<ResumePreview>(`/resume-versions/${id}/preview`); },
  listProjectFiles(id: string) { return request<ProjectFileSummary[]>(`/project-versions/${id}/files`); },
  getProjectFile(id: string) { return request<ProjectFileContent>(`/project-files/${id}`); },
  register(payload: {
    email: string;
    password: string;
    displayName: string;
    role: Exclude<UserRole, "admin">;
  }) {
    return request<AuthData>("/auth/register", {
      method: "POST",
      ...jsonBody(payload),
    });
  },

  login(payload: { email: string; password: string }) {
    return request<AuthData>("/auth/login", {
      method: "POST",
      ...jsonBody(payload),
    });
  },

  getMe() {
    return request<CurrentUser>("/users/me");
  },

  async logout() {
    await request<Record<string, never>>("/auth/logout", { method: "POST" }, false);
  },

  uploadResume(title: string, file: File) {
    const form = new FormData();
    form.append("title", title);
    form.append("file", file);
    return request<ResumeUploadData>("/resumes", { method: "POST", body: form });
  },

  listResumes() {
    return request<ResumeHistory[]>("/resumes");
  },

  listProjects() {
    return request<ProjectHistory[]>("/projects");
  },

  listResumeVersions(id: string) {
    return request<MaterialVersion[]>(`/resumes/${id}/versions`);
  },

  listProjectVersions(id: string) {
    return request<MaterialVersion[]>(`/projects/${id}/versions`);
  },

  createProject(payload: { name: string; description: string; requestId?: string }) {
    return request<ProjectView>("/projects", {
      method: "POST",
      ...jsonBody(payload),
    });
  },

  uploadProjectVersion(projectId: string, file: File, requestId?: string) {
    const form = new FormData();
    form.append("file", file);
    if (requestId) form.append("requestId", requestId);
    return request<ProjectVersionUploadData>(`/projects/${projectId}/versions`, {
      method: "POST",
      body: form,
    });
  },

  getAnalysisTask(taskId: string) {
    return request<AnalysisTask>(`/analysis-tasks/${taskId}`);
  },
  analysisTaskEventsUrl(taskId: string) {
    return `${API_PREFIX}/analysis-tasks/${encodeURIComponent(taskId)}/events`;
  },
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const details = Array.isArray(error.details) ? error.details as ValidationDetail[] : [];
    const first = details[0];
    const field = first?.loc?.at(-1);
    const friendly = field === "email"
      ? "邮箱格式不正确，请检查后重试"
      : field === "password"
        ? "密码格式不符合要求，请检查长度和字符"
        : field === "displayName"
          ? "姓名或昵称格式不正确"
          : first?.msg
            ? `${String(field ?? "参数")}：${first.msg}`
            : error.message;
    return error.requestId ? `${friendly}（请求编号：${error.requestId}）` : friendly;
  }
  if (error instanceof Error) return error.message;
  return "操作失败，请稍后重试";
}
