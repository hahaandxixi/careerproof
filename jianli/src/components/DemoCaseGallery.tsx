"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import DemoCaseImport from "./DemoCaseImport";

type Sample = {
  caseId: string; slug: string; title: string; jobTitle: string; projectTitle: string; boundary: string;
  version: string; resumeName: string; projectName: string; resumeFilename: string; projectFilename: string; scriptFilename: string;
};
const asset = (filename: string) => `/demo-assets/cases/${encodeURIComponent(filename)}`;
const groups = [
  { key: "all", label: "全部" },
  { key: "engineering", label: "开发与运维" },
  { key: "data", label: "数据" },
  { key: "qa", label: "测试" },
  { key: "product", label: "产品与运营" },
] as const;
const groupOf = (slug: string) => slug === "qa" ? "qa" : ["analytics", "data-engineering"].includes(slug) ? "data" : ["product", "operations"].includes(slug) ? "product" : "engineering";

export default function DemoCaseGallery({ samples }: { samples: Sample[] }) {
  const [group, setGroup] = useState<string>("all");
  const visible = useMemo(() => samples.filter(sample => group === "all" || groupOf(sample.slug) === group), [samples, group]);
  return <section className="case-gallery" aria-label="材料库">
    <div className="case-gallery-tabs" role="tablist" aria-label="按方向筛选材料">
      {groups.map(item => <button key={item.key} type="button" role="tab" aria-selected={group === item.key} className={group === item.key ? "is-active" : ""} onClick={() => setGroup(item.key)}>{item.label}<span>{item.key === "all" ? samples.length : samples.filter(sample => groupOf(sample.slug) === item.key).length}</span></button>)}
    </div>
    <div className="case-gallery-grid">
      {visible.map(sample => {
        const jobTitle = sample.jobTitle.replace(/（合成演示）/g, "").trim();
        return <article className="case-card" key={sample.caseId}>
        <div className="case-card-top"><span className="case-id">{sample.version}</span></div>
        <h3>{sample.projectTitle}</h3>
        <p className="case-job">{jobTitle}</p>
        <p className="case-facts">{sample.boundary}</p>
        <div className="case-actions">
          <a href={asset(sample.resumeFilename)} download={sample.resumeFilename}>下载简历</a>
          <a href={asset(sample.projectFilename)} download={sample.projectFilename}>下载项目</a>
          <a href={asset(sample.scriptFilename)} download={sample.scriptFilename}>核对步骤</a>
        </div>
        <DemoCaseImport sample={sample} />
        <Link className="case-find-job" href={`/jobs?q=${encodeURIComponent(jobTitle)}`}>查找对应岗位 →</Link>
      </article>;})}
    </div>
    {!visible.length && <div className="case-gallery-empty" role="status">当前方向暂无材料。</div>}
  </section>;
}


