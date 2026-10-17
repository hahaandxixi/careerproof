import type { NotificationPage } from "./domain";
import type { ReportComparison, Page, JobOptions, Enterprise, JobSummary, JobDetail, JobInput, JobDraftResult, ResumePreview, ProjectFileSummary, ProjectFileContent, ReportSummary, MatchReport, JobRecommendationResult, CareerPlanResult, ApplicationVerificationTask } from "./domain";

const API_PREFIX = "/backend/api/v1";
import type { VisualReview } from "./domain";
import type { EnterpriseReplyContext, GrowthPlan, GrowthTask, PrivateAnswerDraft, PrivateAnswerReferenceOption, PrivateAnswerSave } from "./domain";

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
  materialRole?: "portfolio" | "reference" | null;
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
  isArchived?: boolean;
}

export interface ProjectHistory extends ProjectView {
  createdAt: string;
  versions: MaterialVersion[];
  isArchived?: boolean;
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

async function sharedSessionIsCurrent(): Promise<boolean> {
  const response = await fetch(`${API_PREFIX}/users/me`, {
    credentials: "include", cache: "no-store",
  });
  if (response.status === 401) return false;
  if (!response.ok) {
    const envelope = await readEnvelope<unknown>(response);
    throw new ApiError(envelope?.message ?? "暂时无法确认会话，请稍后重试。", response.status);
  }
  return true;
}

function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    const rotate = async () => {
      const response = await fetch(`${API_PREFIX}/auth/refresh`, {
        method: "POST", credentials: "include", cache: "no-store",
      });
      if (response.status === 401) {
        const envelope = await readEnvelope<unknown>(response);
        if (await sharedSessionIsCurrent()) return true;
        if (envelope?.code === 4015) {
          // Another response may still be delivering the winner's cookie.
          // Never infer logout or token theft from this ambiguous rejection.
          throw new ApiError("会话正在其他窗口恢复，请稍后重试。", 409, 4015);
        }
        return false;
      }
      if (!response.ok) {
        const envelope = await readEnvelope<unknown>(response);
        throw new ApiError(envelope?.message ?? "暂时无法恢复会话，请稍后重试。", response.status, envelope?.code, envelope?.requestId);
      }
      return true;
    };
    refreshInFlight = (async () => {
      if (typeof navigator !== "undefined" && navigator.locks?.request) {
        return navigator.locks.request("careerproof-refresh", async () => {
          // Same-origin tabs share cookies. A previous lock holder may have
          // already refreshed; check before creating another successor.
          if (await sharedSessionIsCurrent()) return true;
          return rotate();
        });
      }
      return rotate();
    })().catch((reason) => {
      if (reason instanceof ApiError) throw reason;
      throw new Error("无法连接服务以确认会话，请检查网络后重试。");
    }).finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  allowRefresh = true,
  responseKind: "json" | "file" = "json",
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, { ...init, credentials: "include", cache: "no-store" });
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
    throw new Error("无法连接服务，请确认网络和后端运行状态后重试。");
  }

  if (response.status === 401 && allowRefresh && !path.startsWith("/auth/")) {
    if (await refreshSession()) return request<T>(path, init, false, responseKind);
  }

  if (response.ok && responseKind === "file") {
    const disposition = response.headers.get("Content-Disposition") ?? "";
    let filename = "resume.txt";
    try { filename = decodeURIComponent(disposition.match(/filename\*=UTF-8''(.+)$/i)?.[1] ?? filename).replace(/[\\/]/g, "_"); } catch { /* Keep a safe download name. */ }
    return { blob: await response.blob(), filename } as T;
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

export interface McpGrant {
  token: string; grantId: string; expiresAt: string; reportIds: string[]; tools: string[];
}

export interface ApplicationView {
  id: string; jobId: string; jobTitle: string; companyName: string; candidateName: string;
  reportId: string; status: string; createdAt: string; overallScore: number | null;
  consentVersion: string; replyKind: string | null; replyText: string | null;
  replyReferences: { requirementId: string; citationIds: string[] }[];
  comparisonBasis: string;
  events: { type: string; at: string; detail: string }[];
  dimensions: { requirementId: string; title: string; skill: string; score: number | null; verdict: string; weight: number; evidenceLevel: number | null; evidenceLevelSource: string | null; evidenceLevelVersion: string | null; formulaVersion: string | null }[];
  report?: MatchReport;
}

function applicationEvent<T>(result: Promise<T>) {
  return result.then(value => { if (typeof window !== "undefined") window.dispatchEvent(new Event("notifications-changed")); return value; });
}

export const api = {
  notifications(page = 1, unreadOnly = false, pageSize = 20) { return request<NotificationPage>(`/notifications?page=${page}&pageSize=${pageSize}&unread_only=${unreadOnly}`); },
  notificationCount() { return request<{ unreadCount: number }>("/notifications/unread-count"); },
  readNotification(id: string) { return request<{ unreadCount: number }>(`/notifications/${id}/read`, { method: "POST" }); },
  readAllNotifications() { return request<{ unreadCount: number }>("/notifications/read-all", { method: "POST" }); },
  notificationTarget(id: string) { return request<{ href: string }>(`/notifications/${id}/target`); },
  createApplication(reportId: string) { return applicationEvent(request<ApplicationView>("/applications", { method: "POST", ...jsonBody({ reportId, shareConsent: true }) })); },
  applicationDetail(id: string) { return request<ApplicationView>(`/applications/${id}`); },
  myApplications(page = 1, pageSize = 20, jobId?: string) { const query = new URLSearchParams({ page: String(page), pageSize: String(pageSize) }); if (jobId) query.set("jobId", jobId); return request<Page<ApplicationView>>(`/applications/mine?${query}`); },
  jobApplications(jobId: string, page = 1, pageSize = 20) { return request<Page<ApplicationView>>(`/jobs/${jobId}/applications?page=${page}&pageSize=${pageSize}`); },
  openApplication(id: string) { return applicationEvent(request<ApplicationView>(`/applications/${id}/view`, { method: "POST" })); },
  replyApplication(id: string, kind: string, text: string, references: ApplicationView["replyReferences"] = []) { return applicationEvent(request<ApplicationView>(`/applications/${id}/reply`, { method: "POST", ...jsonBody({ kind, text, references }) })); },
  withdrawApplication(id: string) { return applicationEvent(request<ApplicationView>(`/applications/${id}/withdraw`, { method: "POST" })); },
  downloadApplicationResume(id: string) { return applicationEvent(request<{blob: Blob; filename: string}>(`/applications/${id}/resume-download`, { method: "POST" }, true, "file")); },
  createApplicationVerification(id: string, signal?: AbortSignal) {
    return request<ApplicationVerificationTask>(`/applications/${encodeURIComponent(id)}/verification`, { method: "POST", signal, ...jsonBody({ externalAiConsent: true }) });
  },
  applicationVerification(id: string, taskId?: string, signal?: AbortSignal) {
    const suffix = taskId ? `/${encodeURIComponent(taskId)}` : "";
    return request<ApplicationVerificationTask | null>(`/applications/${encodeURIComponent(id)}/verification${suffix}`, { signal });
  },
  archiveMaterial(kind: "resume" | "project", id: string, archived: boolean) { return request<{archived:boolean}>(`/materials/${kind}/${id}/archive`, { method: "PATCH", ...jsonBody({ archived }) }); },
  issueMcpGrant(reportIds: string[]) {
    return request<McpGrant>("/mcp-tools/grants", { method: "POST", ...jsonBody({ report_ids: reportIds, external_client_consent: true }) });
  },
  revokeMcpGrant(id: string) { return request<{ revoked: boolean }>(`/mcp-tools/grants/${id}`, { method: "DELETE" }); },
  getVisualReview(id: string) { return request<VisualReview | null>(`/project-versions/${id}/visual-review`); },
  observeImage(id: string) { return request<VisualReview>(`/project-versions/${id}/visual-review`, { method: "POST", ...jsonBody({ externalImageConsent: true }) }); },
  reviewVisual(id: string, status: VisualReview["reviewStatus"], note: string) { return request<VisualReview>(`/visual-reviews/${id}`, { method: "PATCH", ...jsonBody({ status, note }) }); },
  listJobs(filters: Record<string, string | number> = {}, mine = false) {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value !== "") query.set(key, String(value)); });
    return request<Page<JobSummary>>(`/jobs${mine ? "/mine" : ""}?${query}`);
  },
  jobOptions() { return request<JobOptions>("/jobs/options"); },
  getJob(id: string) { return request<JobDetail>(`/jobs/${id}`); },
  createJob(payload: JobInput) { return request<JobDetail>("/jobs", { method: "POST", ...jsonBody(payload) }); },
  draftJobRequirements(payload: { description: string; externalAiConsent: boolean }) {
    return request<JobDraftResult>("/jobs/ai-draft", { method: "POST", ...jsonBody(payload) });
  },
  updateJob(id: string, payload: Partial<Omit<JobInput, "enterpriseId" | "companyName">>) {
    return request<JobDetail>(`/jobs/${id}`, { method: "PATCH", ...jsonBody(payload) });
  },
  listEnterprises() { return request<Enterprise[]>("/enterprises/me"); },
  createEnterprise(payload: { name: string; description: string }) {
    return request<Enterprise>("/enterprises", { method: "POST", ...jsonBody(payload) });
  },
  createMatch(payload: { jobId: string; resumeVersionId: string; projectVersionIds: string[]; externalAiConsent: boolean; usePreviousReport?: boolean }) {
    return request<{ taskId: string; status: TaskStatus }>("/matches", { method: "POST", ...jsonBody(payload) });
  },
  recommendJobs(payload: { resumeVersionId: string; projectVersionIds: string[]; limit?: number }) {
    return request<JobRecommendationResult>("/job-recommendations", { method: "POST", ...jsonBody(payload) });
  },
  createCareerPlan(payload: { resumeVersionId: string; projectVersionIds: string[]; limit?: number; externalAiConsent: boolean }) {
    return request<CareerPlanResult>("/career-plans", { method: "POST", ...jsonBody(payload) });
  },
  latestCareerPlan() { return request<CareerPlanResult | null>("/career-plans/latest"); },
  listReports(page = 1, pageSize = 20) { return request<Page<ReportSummary>>(`/match-reports?page=${page}&pageSize=${pageSize}`); },
  previousComparison(id: string) { return request<ReportComparison | null>(`/match-reports/${id}/previous-comparison`); },
  existingGrowthTask(reportId: string, requirementId: string) { return request<GrowthTask | null>(`/match-reports/${reportId}/growth-tasks/${requirementId}`); },
  enterpriseReplyContext(reportId: string, requirementId: string) { return request<EnterpriseReplyContext | null>(`/match-reports/${reportId}/enterprise-replies/${requirementId}`); },
  createGrowthTask(reportId: string, plan: GrowthPlan) { return request<GrowthTask>(`/match-reports/${reportId}/growth-tasks`, { method: "POST", ...jsonBody(plan) }); },
  listGrowthTasks(page = 1, pageSize = 20) { return request<Page<GrowthTask> & { unavailableCount: number }>(`/growth-tasks?page=${page}&pageSize=${pageSize}`); },
  growthTask(id: string) { return request<GrowthTask>(`/growth-tasks/${id}`); },
  growthMaterials(id: string, payload: { resumeVersionId: string; projectVersionIds: string[]; targetJobId?: string }) {
    // 可省略 targetJobId=沿用原岗位；undefined 不会被 JSON 序列化。
    const { targetJobId, ...materials } = payload;
    return request<GrowthTask>(`/growth-tasks/${id}/materials`, { method: "PUT", ...jsonBody(targetJobId ? { ...materials, targetJobId } : materials) });
  },
  analyzeGrowth(id: string, externalAiConsent: boolean) { return request<GrowthTask>(`/growth-tasks/${id}/analyze`, { method: "POST", ...jsonBody({ externalAiConsent }) }); },
  // PRODUCT-01 私人回答草稿：只读写本人草稿与可选引用，不触发分析、通知或任何外发。
  getAnswerDraft(taskId: string) { return request<PrivateAnswerDraft | null>(`/growth-tasks/${taskId}/answer-draft`); },
  saveAnswerDraft(taskId: string, payload: PrivateAnswerSave) { return request<PrivateAnswerDraft>(`/growth-tasks/${taskId}/answer-draft`, { method: "PUT", ...jsonBody(payload) }); },
  listAnswerDraftReferences(taskId: string) { return request<PrivateAnswerReferenceOption[]>(`/growth-tasks/${taskId}/answer-draft/references`); },
  getReport(id: string) { return request<MatchReport>(`/match-reports/${id}`); },
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

  listResumes(includeArchived = false) {
    return request<ResumeHistory[]>(`/resumes${includeArchived ? "?includeArchived=true" : ""}`);
  },

  listProjects(includeArchived = false) {
    return request<ProjectHistory[]>(`/projects${includeArchived ? "?includeArchived=true" : ""}`);
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

  uploadProjectVersion(projectId: string, file: File, requestId?: string, materialRole: "portfolio" | "reference" = "portfolio") {
    const form = new FormData();
    form.append("file", file);
    if (requestId) form.append("requestId", requestId);
    form.append("materialRole", materialRole);
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
