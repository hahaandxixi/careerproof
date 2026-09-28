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
