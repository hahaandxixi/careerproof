interface ResumeVersion {
  id: string;
  versionNumber: number;
  originalFilename: string | null;
  status: string;
}

interface Resume<V extends ResumeVersion> {
  id: string;
  title: string;
  versions: V[];
}

// Display categories only: no deletion, renaming, or change to material permissions.
// Match known legacy fixture prefixes conservatively; unknown titles stay in the main list.
const LEGACY_FIXTURE = /^(?:历史难例合成简历$|历史验收简历 \d{8}|(?:数据库工程师 DBA|自动化运维工程师)验收简历\d{4}$|Function Calling 合成简历 ?\d{8}|AI完整报告合成简历 ?\d{8}|浏览器(?:全链路|完整链路)(?:合成)?简历[- ]?\d{8}|OCR合成烟测[- ]?\d{8}|开源归属回归[:：])/u;

export function resumeDisplayCategory(title: string, demoTitles: readonly string[]) {
  if (demoTitles.includes(title)) return "demo" as const;
  return LEGACY_FIXTURE.test(title) ? "history" as const : "personal" as const;
}

export function filterResumeMaterials<V extends ResumeVersion>(
  resumes: Resume<V>[], query: string, includeHistory: boolean, demoTitles: readonly string[],
) {
  const search = query.trim().toLocaleLowerCase();
  return resumes.flatMap(resume => {
    const category = resumeDisplayCategory(resume.title, demoTitles);
    // Searching includes archived display groups, so hidden items remain discoverable.
    if (category === "history" && !includeHistory && !search) return [];
    const titleMatches = resume.title.toLocaleLowerCase().includes(search);
    const versions = resume.versions.filter(version => version.status === "completed" && (
      !search || titleMatches || `${version.originalFilename ?? ""} 第 ${version.versionNumber} 版`
        .toLocaleLowerCase().includes(search)
    )).sort((left, right) => right.versionNumber - left.versionNumber);
    return versions.length ? [{ ...resume, category, versions }] : [];
  });
}

// 同名简历在版本选择器里必须仍可区分：两版同名简历会渲染出完全相同的标题，
// 单选按钮的无障碍名也会重复，读屏用户无法判断自己选的是哪一份。
// 与 projects 侧的 duplicateProjectNames/projectNameLabel 保持同一显示口径：
// 只在标题确实重复时才补编号前8位，标题唯一的常见情况不增加噪声。
export function duplicateResumeTitles(resumes: { title: string }[]): Set<string> {
  const counts = new Map<string, number>();
  for (const resume of resumes) counts.set(resume.title, (counts.get(resume.title) ?? 0) + 1);
  return new Set([...counts].filter(([, count]) => count > 1).map(([title]) => title));
}

export function resumeTitleLabel(title: string, id: string, duplicateTitles: ReadonlySet<string>): string {
  return duplicateTitles.has(title) ? `${title} · 材料编号 ${id.slice(0, 8)}` : title;
}
