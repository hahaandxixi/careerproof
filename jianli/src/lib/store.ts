import type { Candidate, Job, MatchResult } from "./types";
import { jobs as seedJobs, candidates as seedCandidates } from "./data";
import { runMatchPipeline } from "./agent/pipeline";

/**
 * 内存数据仓库（MVP 阶段）。
 * 说明：演示数据仅存于内存，服务重启后回到种子状态；
 * 后续可替换为真实数据库（Postgres/向量库）以支撑 RAG 与持久化。
 */

let jobs: Job[] = [...seedJobs];

export function getJobs(): Job[] {
  return jobs;
}

export function getJob(id: string): Job | undefined {
  return jobs.find((j) => j.id === id);
}

export function addJob(job: Job): Job {
  jobs = [job, ...jobs];
  return job;
}

export function getCandidates(): Candidate[] {
  return seedCandidates;
}

export function getCandidate(id: string): Candidate | undefined {
  return seedCandidates.find((c) => c.id === id);
}

export async function getMatch(jobId: string, candidateId: string): Promise<MatchResult | null> {
  const job = getJob(jobId);
  const candidate = getCandidate(candidateId);
  if (!job || !candidate) return null;
  const { result } = await runMatchPipeline(job, candidate);
  return result;
}

export async function listJobMatches(jobId: string): Promise<
  { candidate: Candidate; result: MatchResult }[]
> {
  const job = getJob(jobId);
  if (!job) return [];
  const out = [];
  for (const c of seedCandidates) {
    const { result } = await runMatchPipeline(job, c);
    out.push({ candidate: c, result });
  }
  return out.sort((a, b) => b.result.overallScore - a.result.overallScore);
}
