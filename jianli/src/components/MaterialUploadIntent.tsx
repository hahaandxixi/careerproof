"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { ProjectHistory } from "@/lib/api/client";

// A navigation hint only opens a form. Owned history resolves the target; no upload or analysis runs.
export default function MaterialUploadIntent({ projects, ready, onOpen }: { projects: ProjectHistory[]; ready: boolean; onOpen(projectId?: string): boolean }) {
  const query = useSearchParams();
  const add = query.get("add"), version = query.get("sourceProjectVersion");
  const handled = useRef("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!ready || add !== "project") return;
    const key = `${add}:${version || ""}`;
    if (handled.current === key) return;
    handled.current = key;
    const project = version ? projects.find(value => value.versions.some(item => item.id === version)) : undefined;
    if (version && !project) { setNotice("原项目不在当前材料库，请核对账号或归档材料后选择上传目标。"); return; }
    setNotice(onOpen(project?.id) ? "" : "当前有未完成的上传，请先处理后再切换项目。");
  }, [add, version, ready, projects, onOpen]);
  return notice ? <p role="status" className="text-sm text-amber-800">{notice}</p> : null;
}
