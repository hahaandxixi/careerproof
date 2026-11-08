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
  { key: "engineering", label: "后端与运维" },
  { key: "data", label: "数据" },
  { key: "qa", label: "测试" },
  { key: "product", label: "产品与运营" },
] as const;
const groupOf = (slug: string) => slug === "qa" ? "qa" : ["analytics", "data-engineering"].includes(slug) ? "data" : ["product", "operations"].includes(slug) ? "product" : "engineering";
const domainMeta: Record<string, { domain: string; label: string }> = {
  engineering: { domain: "backend", label: "后端" },
  data: { domain: "data", label: "数据" },
  qa: { domain: "testing", label: "测试" },
  product: { domain: "tools", label: "产品与运营" },
};
const domainOf = (slug: string) => {
  if (slug === "frontend") return { domain: "frontend", label: "前端" };
  if (slug === "qa") return domainMeta.qa;
  if (["analytics", "data-engineering"].includes(slug)) return domainMeta.data;
  if (["product", "operations"].includes(slug)) return domainMeta.product;
  if (slug === "backend") return domainMeta.engineering;
  return { domain: "tools", label: "工具与未知" };
};

export default function DemoCaseGallery({ samples }: { samples: Sample[] }) {
  const [group, setGroup] = useState<string>("all");
  const visible = useMemo(() => samples.filter(sample => group === "all" || groupOf(sample.slug) === group), [samples, group]);
  return <section className="case-gallery" aria-label="案例库">
    <div className="case-gallery-tabs" role="tablist" aria-label="按方向筛选案例">
      {groups.map(item => <button key={item.key} type="button" role="tab" aria-selected={group === item.key} className={group === item.key ? "is-active" : ""} onClick={() => setGroup(item.key)}>{item.label}<span>{item.key === "all" ? samples.length : samples.filter(sample => groupOf(sample.slug) === item.key).length}</span></button>)}
    </div>
    <div className="case-gallery-grid">
      {visible.map(sample => {
        const domain = domainOf(sample.slug);
        return <article className="case-card" key={sample.caseId}>
        <div className="case-card-top"><span className="case-id">{sample.caseId} · {sample.version}</span><span className="tech-tag" data-domain={domain.domain}>{domain.label}</span><span className="case-synthetic">合成案例</span></div>
        <h3>{sample.title}</h3>
        <p className="case-project">{sample.projectTitle}</p>
        <p className="case-job">{sample.jobTitle}</p>
        <dl className="case-facts"><div><dt>边界</dt><dd>{sample.boundary}</dd></div></dl>
        <div className="case-actions">
          <a href={asset(sample.resumeFilename)} download={sample.resumeFilename}>下载简历</a>
          <a href={asset(sample.projectFilename)} download={sample.projectFilename}>下载项目</a>
          <a href={asset(sample.scriptFilename)} download={sample.scriptFilename}>测试步骤</a>
        </div>
        <DemoCaseImport sample={sample} />
        <Link className="case-find-job" href={`/jobs?q=${encodeURIComponent(sample.jobTitle.replace(/（合成演示）/g, "").trim())}`}>查找对应岗位 →</Link>
      </article>;})}
    </div>
    {!visible.length && <div className="case-gallery-empty" role="status">当前方向暂无案例。</div>}
  </section>;
}


