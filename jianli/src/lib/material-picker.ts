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
    ));
    return versions.length ? [{ ...project, versions }] : [];
  });
}

export function toggleMaterialVersion(selected: string[], id: string, checked: boolean) {
  if (!checked) return selected.filter(value => value !== id);
  if (selected.includes(id) || selected.length >= 10) return selected;
  return [...selected, id];
}
