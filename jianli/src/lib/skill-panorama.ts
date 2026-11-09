import type { MatchReport, Page, ReportItem, ReportSummary } from "./api/domain.ts";

export const PANORAMA_PAGE_SIZE = 12;
export const PANORAMA_CONCURRENCY = 3;
export const PANORAMA_STATUSES = ["supported", "partial", "claimed_only", "gap", "unsupported", "unknown"] as const;
export type PanoramaStatus = typeof PANORAMA_STATUSES[number];
export const PANORAMA_STATUS_LABELS: Record<PanoramaStatus, string> = {
  supported: "有证据支持", partial: "部分支持", claimed_only: "仅简历声明",
  gap: "材料待补充", unsupported: "规则暂未支持", unknown: "状态未知 / 未评估",
};
export type StatusCounts = Record<PanoramaStatus, number>;
export const PANORAMA_FILTERS = ["all", "supported", "partial", "claimed_only", "gap"] as const;
export type PanoramaFilter = typeof PANORAMA_FILTERS[number];
export const PANORAMA_FILTER_LABELS: Record<PanoramaFilter, string> = {
  all: "全部记录", supported: "有证据支持", partial: "部分支持", claimed_only: "仅简历声明", gap: "待补材料",
};
/** One record can match several views; the original saved status is never rewritten. */
export function panoramaFilterMatches(status: PanoramaStatus, filter: PanoramaFilter): boolean {
  return filter === "all" || status === filter;
}
export function filterSkillContexts(contexts: SkillContext[], filter: PanoramaFilter): SkillContext[] {
  return contexts.filter(context => panoramaFilterMatches(panoramaStatus(context.item.verdict), filter));
}
export function skillJobCount(contexts: SkillContext[]): number {
  return new Set(contexts.map(context => context.jobId)).size;
}
export interface JobContextGroup { jobId: string; jobTitle: string; contexts: SkillContext[]; }
/** Group by the saved jobId, never by a display title that two jobs may share. */
export function groupContextsByJob(contexts: SkillContext[]): JobContextGroup[] {
  const groups = new Map<string, JobContextGroup>();
  for (const context of contexts) {
    const group = groups.get(context.jobId);
    if (group) { group.contexts.push(context); continue; }
    groups.set(context.jobId, { jobId: context.jobId, jobTitle: context.jobTitle, contexts: [context] });
  }
  for (const group of groups.values()) {
    group.contexts.sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
    // The newest saved report is shown first, but only an explicit server flag is
    // ever labelled "最新报告"; recency in a loaded batch is not a global claim.
    const flagged = group.contexts.find(context => context.isLatestForJob === true);
    if (flagged && group.contexts[0] !== flagged) {
      group.contexts = [flagged, ...group.contexts.filter(context => context !== flagged)];
    }
  }
  return [...groups.values()].sort((a, b) =>
    (Date.parse(b.contexts[0]?.createdAt ?? "") || 0) - (Date.parse(a.contexts[0]?.createdAt ?? "") || 0));
}
export interface SkillContext {
  key: string; reportId: string; jobId: string; jobTitle: string; createdAt: string;
  isLatestForJob?: boolean; materials: MatchReport["materials"]; item: ReportItem;
}
export interface PanoramaSkill {
  key: string; name: string; category: string; contexts: SkillContext[]; counts: StatusCounts;
}

// Exact display grouping only, not an ontology, alias resolver or ability taxonomy.
const categories: [string, string[]][] = [
  ["编程语言", ["python", "java", "javascript", "typescript", "c", "c++", "c#", "go", "rust", "r"]],
  ["数据与存储", ["sql", "mysql", "postgresql", "redis", "mongodb", "pandas", "numpy", "excel", "数据分析", "数据清洗"]],
  ["框架与应用", ["react", "vue", "django", "flask", "fastapi", "spring", "spring boot", "node.js", "html", "css"]],
  ["工程与协作", ["git", "linux", "docker", "kubernetes", "pytest", "单元测试", "软件测试", "沟通", "团队协作"]],
];
export const PANORAMA_CATEGORIES = [...categories.map(([name]) => name), "其他 / 未分类"];
export function skillDisplayName(value: string): string { return value.trim().replace(/\s+/g, " "); }
export function panoramaStatus(verdict: string): PanoramaStatus {
  if (verdict === "verified") return "supported";
  return PANORAMA_STATUSES.includes(verdict as PanoramaStatus) ? verdict as PanoramaStatus : "unknown";
}
export function countContexts(contexts: SkillContext[]): StatusCounts {
  const counts = Object.fromEntries(PANORAMA_STATUSES.map(status => [status, 0])) as StatusCounts;
  for (const context of contexts) counts[panoramaStatus(context.item.verdict)]++;
  return counts;
}
export function buildSkillPanorama(reports: MatchReport[]) {
  const grouped = new Map<string, PanoramaSkill>(), unclassified: SkillContext[] = [], seen = new Set<string>();
  for (const report of reports) for (const item of report.items) {
    const key = JSON.stringify([report.id, item.requirementId]);
    if (seen.has(key)) continue;
    seen.add(key);
    const context: SkillContext = { key, reportId: report.id, jobId: report.jobId, jobTitle: report.jobTitle,
      createdAt: report.createdAt, isLatestForJob: report.isLatestForJob, materials: report.materials, item };
    const name = skillDisplayName(item.skill || "");
    if (!name) { unclassified.push(context); continue; }
    const normalized = name.toLowerCase();
    if (!grouped.has(normalized)) grouped.set(normalized, { key: normalized, name,
      category: categories.find(([, names]) => names.includes(normalized))?.[0] ?? "其他 / 未分类",
      contexts: [], counts: countContexts([]) });
    grouped.get(normalized)!.contexts.push(context);
  }
  const skills = [...grouped.values()].map(skill => ({ ...skill, counts: countContexts(skill.contexts) }));
  const contexts = [...skills.flatMap(skill => skill.contexts), ...unclassified];
  return { skills, unclassified, counts: countContexts(contexts), contextCount: contexts.length };
}

/** Keep the selected skill while it has a record in the new filter; otherwise move
 * to the first skill that does, so the rail never describes a hidden card. */
export function selectionForFilter(landscape: ReturnType<typeof buildSkillPanorama>, selected: string | null, filter: PanoramaFilter): string | null {
  if (selected === null) return null;
  const contexts = selected === "" ? landscape.unclassified : landscape.skills.find(skill => skill.key === selected)?.contexts ?? [];
  if (filterSkillContexts(contexts, filter).length) return selected;
  const first = landscape.skills.find(skill => filterSkillContexts(skill.contexts, filter).length);
  if (first) return first.key;
  return filterSkillContexts(landscape.unclassified, filter).length ? "" : null;
}

export interface PanoramaState {
  summaries: ReportSummary[]; reports: MatchReport[]; total: number | null;
  failures: Record<string, string>; listError: string; busy: boolean; hasMore: boolean; blocked: boolean;
}
export function initialPanoramaState(): PanoramaState {
  return { summaries: [], reports: [], total: null, failures: {}, listError: "", busy: false, hasMore: true, blocked: false };
}

/** One account, one bounded batch. No persistence, prefetch loop, report writes or latest inference. */
export function createSkillPanoramaSession(ownerId: string, api: {
  listReports(page: number, pageSize: number, filters?: { scope?: "product" | "all" }): Promise<Page<ReportSummary>>;
  getReport(id: string): Promise<MatchReport>;
  errorMessage(error: unknown): string;
}, publish: (state: PanoramaState) => void) {
  let state = initialPanoramaState(), active = false, generation = 0, nextPage = 1;
  const update = (patch: Partial<PanoramaState>) => { state = { ...state, ...patch }; publish(state); };
  const current = (ticket: number) => active && ticket === generation && !state.blocked;
  function block(message: string) {
    generation++;
    update({ ...initialPanoramaState(), blocked: true, hasMore: false, listError: message });
  }
  function identityFailure() { block("报告归属与当前账号不一致，已清空本次读取。请重新确认登录账号。"); }
  function sessionFailure(error: unknown): boolean {
    if ((error as { status?: number } | null)?.status !== 401) return false;
    block("登录状态已失效，已清空本次读取。请重新登录后查看。");
    return true;
  }
  async function details(ids: string[], ticket: number) {
    let cursor = 0;
    await Promise.all(Array.from({ length: Math.min(PANORAMA_CONCURRENCY, ids.length) }, async () => {
      while (current(ticket) && cursor < ids.length) {
        const id = ids[cursor++];
        try {
          const report = await api.getReport(id);
          if (!current(ticket)) return;
          const summary = state.summaries.find(value => value.id === id);
          if (report.id !== id || report.candidateId !== ownerId || report.jobId !== summary?.jobId) { identityFailure(); return; }
          const failures = { ...state.failures }; delete failures[id];
          update({ reports: [...state.reports.filter(value => value.id !== id), report], failures });
        } catch (error) {
          if (!current(ticket) || sessionFailure(error)) return;
          update({ failures: { ...state.failures, [id]: api.errorMessage(error) } });
        }
      }
    }));
  }
  return {
    activate() { active = true; generation++; nextPage = 1; update(initialPanoramaState()); },
    dispose() { active = false; generation++; },
    async loadMore() {
      if (!active || state.busy || !state.hasMore || state.blocked) return;
      const ticket = generation;
      update({ busy: true, listError: "" });
      try {
        const page = await api.listReports(nextPage, PANORAMA_PAGE_SIZE, { scope: "product" });
        if (!current(ticket)) return;
        if (page.items.some(report => report.candidateId !== ownerId)) { identityFailure(); return; }
        const fresh = page.items.filter(report => !state.summaries.some(value => value.id === report.id));
        const summaries = [...state.summaries, ...fresh];
        nextPage = page.page + 1;
        update({ summaries, total: page.total, hasMore: fresh.length > 0 && summaries.length < page.total && page.page * page.pageSize < page.total });
        await details(fresh.map(report => report.id), ticket);
      } catch (error) {
        if (current(ticket) && !sessionFailure(error)) update({ listError: api.errorMessage(error) });
      } finally { if (current(ticket)) update({ busy: false }); }
    },
    async retryFailed() {
      if (!active || state.busy || state.blocked) return;
      const ticket = generation;
      update({ busy: true });
      try { await details(Object.keys(state.failures), ticket); }
      finally { if (current(ticket)) update({ busy: false }); }
    },
  };
}

