interface Version {
  id: string;
  versionNumber: number;
  originalFilename: string | null;
  status: string;
}

interface Project<V extends Version> {
  id: string;
  name: string;
  versions: V[];
}

// Filtering changes visibility only. Selection stays in the parent form.
export function filterMaterialProjects<V extends Version>(projects: Project<V>[], query: string) {
  const search = query.trim().toLocaleLowerCase();
  return projects.flatMap(project => {
    const nameMatches = project.name.toLocaleLowerCase().includes(search);
    const versions = project.versions.filter(version => version.status === "completed" && (
      !search || nameMatches || `${version.originalFilename ?? ""} 第 ${version.versionNumber} 版`
        .toLocaleLowerCase().includes(search)
    )).sort((left, right) => right.versionNumber - left.versionNumber);
    return versions.length ? [{ ...project, versions }] : [];
  });
}

const LEGACY_PROJECT = /^(?:历史验收项目 \d{8}|视觉(?:与代码组合)?合成验收 \d{8}|Function Calling 合成项目 ?\d{8}|AI完整报告合成项目 ?\d{8}|浏览器(?:全链路|完整链路)(?:合成)?项目[- ]?\d{8}|历史完整报告 |合成视觉并发 |开源归属回归[:：])/u;

export function projectDisplayCategory(name: string, demoNames: readonly string[]) {
  if (demoNames.includes(name)) return "demo" as const;
  return LEGACY_PROJECT.test(name) ? "history" as const : "personal" as const;
}

export function groupMaterialProjects<V extends Version>(projects: Project<V>[], query: string, includeHistory: boolean, demoNames: readonly string[]) {
  return filterMaterialProjects(projects, query).flatMap(project => {
    const category = projectDisplayCategory(project.name, demoNames);
    return category === "history" && !includeHistory && !query.trim() ? [] : [{ ...project, category }];
  });
}

export function toggleMaterialVersion(selected: string[], id: string, checked: boolean) {
  if (!checked) return selected.filter(value => value !== id);
  if (selected.includes(id) || selected.length >= 10) return selected;
  return [...selected, id];
}

// 同名项目在选择器里必须仍可区分，否则用户会选错材料、生成基于错误项目的报告。
// 只在名称确实重复时才补编号，常见情况（名称唯一）不增加噪声。
export function duplicateProjectNames(projects: { name: string }[]): Set<string> {
  const counts = new Map<string, number>();
  for (const project of projects) counts.set(project.name, (counts.get(project.name) ?? 0) + 1);
  return new Set([...counts].filter(([, count]) => count > 1).map(([name]) => name));
}

export function projectNameLabel(name: string, id: string, duplicateNames: ReadonlySet<string>): string {
  return duplicateNames.has(name) ? `${name} · 材料编号 ${id.slice(0, 8)}` : name;
}
