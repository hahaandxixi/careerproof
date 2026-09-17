import type { ProjectView, ProjectVersionUploadData } from "./api/client";

// One logical creation and upload keeps these keys until a confirmed response.
// File bytes and authentication credentials are never saved in browser storage.
export interface ProjectAttempt {
  createRequestId: string;
  uploadRequestId: string;
  name: string;
  description: string;
  project: ProjectView | null;
}

export function newProjectAttempt(
  name: string, description: string, project: ProjectView | null = null
): ProjectAttempt {
  return {
    createRequestId: crypto.randomUUID(), uploadRequestId: crypto.randomUUID(),
    name, description, project,
  };
}

interface ProjectApi {
  createProject(payload: {
    name: string; description: string; requestId: string;
  }): Promise<ProjectView>;
  uploadProjectVersion(id: string, file: File, requestId: string): Promise<ProjectVersionUploadData>;
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
  return client.uploadProjectVersion(current.project!.id, file, current.uploadRequestId);
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
