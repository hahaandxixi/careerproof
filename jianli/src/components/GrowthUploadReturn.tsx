"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

export default function GrowthUploadReturn() {
  const id = useSearchParams().get("growthTask");
  if (!id || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) return null;
  return <aside className="panel space-y-2 border-indigo-200 text-sm"><p>正在为补证任务准备材料。给原项目上传具名新版，旧材料与企业投递不被覆盖；解析完成后回任务明确选择版本。</p><Link className="text-indigo-700 underline" href={`/growth/${id}`}>返回补证任务并读取材料 →</Link></aside>;
}
