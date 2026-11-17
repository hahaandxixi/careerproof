import type { ProjectView, ProjectVersionUploadData } from "./api/client";

// One logical creation and upload keeps these keys until a confirmed response.
// File bytes and authentication credentials are never saved in browser storage.
export interface ProjectAttempt {
  createRequestId: string;
  uploadRequestId: string;
  name: string;
  description: string;
  materialRole: "portfolio" | "reference";
  project: ProjectView | null;
}

export function newProjectAttempt(
  name: string, description: string, project: ProjectView | null = null,
  materialRole: "portfolio" | "reference" = "portfolio"
): ProjectAttempt {
  return {
    createRequestId: crypto.randomUUID(), uploadRequestId: crypto.randomUUID(),
    name, description, materialRole, project,
  };
}

interface ProjectApi {
  createProject(payload: {
    name: string; description: string; requestId: string;
  }): Promise<ProjectView>;
  uploadProjectVersion(id: string, file: File, requestId: string, materialRole: "portfolio" | "reference"): Promise<ProjectVersionUploadData>;
}

export async function submitProjectAttempt(
  client: ProjectApi,
  attempt: ProjectAttempt,
  file: File,
  remember: (next: ProjectAttempt) => void
): Promise<ProjectVersionUploadData> {
  let current = attempt;
  if (!current.project) {
    const project = await client.createProject({
      name: current.name, description: current.description, requestId: current.createRequestId,
    });
    current = { ...current, project };
    // Persist immediately, before starting the upload that might fail.
    remember(current);
  }
  return client.uploadProjectVersion(current.project!.id, file, current.uploadRequestId, current.materialRole);
}

export function readAttempt(storage: Storage, userId: string): ProjectAttempt | null {
  try {
    const value = JSON.parse(storage.getItem(`careerproof:project-attempt:${userId}`) ?? "null");
    if (!value || typeof value.name !== "string" || typeof value.description !== "string"
      || typeof value.createRequestId !== "string" || typeof value.uploadRequestId !== "string"
      || (value.project !== null && (typeof value.project?.id !== "string"
        || typeof value.project?.name !== "string" || typeof value.project?.description !== "string"))) {
      return null;
    }
    if (value.materialRole !== "portfolio" && value.materialRole !== "reference") {
      value.materialRole = "portfolio";
    }
    return value as ProjectAttempt;
  } catch {
    return null;
  }
}

export function writeAttempt(storage: Storage, userId: string, value: ProjectAttempt | null) {
  try {
    const key = `careerproof:project-attempt:${userId}`;
    if (value) storage.setItem(key, JSON.stringify(value));
    else storage.removeItem(key);
  } catch {
    // Storage restrictions do not prevent this tab from retaining the request in memory.
  }
}

export interface ResumeAttempt {
  requestId: string;
  title: string;
  filename: string;
  size: number;
  lastModified: number;
}

export function newResumeAttempt(title: string, file: File): ResumeAttempt {
  return {
    requestId: crypto.randomUUID(),
    title,
    filename: file.name,
    size: file.size,
    lastModified: file.lastModified,
  };
}

export function resumeAttemptMatches(attempt: ResumeAttempt | null, title: string, file: File | null): attempt is ResumeAttempt {
  return !!attempt && !!file && attempt.title === title && attempt.filename === file.name
    && attempt.size === file.size && attempt.lastModified === file.lastModified;
}

const RESUME_ATTEMPT_PREFIX = "careerproof:resume-attempt:";

export function readResumeAttempt(storage: Storage, userId: string): ResumeAttempt | null {
  try {
    const value = JSON.parse(storage.getItem(`${RESUME_ATTEMPT_PREFIX}${userId}`) ?? "null");
    return value && typeof value.requestId === "string" && typeof value.title === "string"
      && typeof value.filename === "string" && Number.isFinite(value.size)
      && Number.isFinite(value.lastModified) ? value as ResumeAttempt : null;
  } catch {
    return null;
  }
}

export function writeResumeAttempt(storage: Storage, userId: string, value: ResumeAttempt | null) {
  try {
    const key = `${RESUME_ATTEMPT_PREFIX}${userId}`;
    if (value) storage.setItem(key, JSON.stringify(value));
    else storage.removeItem(key);
  } catch {
    // The current tab retains the attempt in memory.
  }
}
