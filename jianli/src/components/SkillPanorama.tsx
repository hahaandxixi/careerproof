"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import {
  buildSkillPanorama, createSkillPanoramaSession, initialPanoramaState,
  PANORAMA_CATEGORIES, PANORAMA_PAGE_SIZE, PANORAMA_STATUSES, PANORAMA_STATUS_LABELS, panoramaStatus,
  type PanoramaState, type SkillContext, type StatusCounts,
} from "@/lib/skill-panorama";
import AccessGate from "./AccessGate";
import { useAuth } from "./AuthProvider";
import styles from "./SkillPanorama.module.css";

const skillDomains: Record<string, { domain: string; label: string }> = {};
for (const name of ["python", "java", "javascript", "c", "c++", "c#", "go", "rust", "r", "django", "flask", "fastapi", "spring", "spring boot", "node.js"]) skillDomains[name] = { domain: "backend", label: "后端" };
for (const name of ["react", "vue", "typescript", "html", "css"]) skillDomains[name] = { domain: "frontend", label: "前端" };
for (const name of ["sql", "mysql", "postgresql", "redis", "mongodb", "pandas", "numpy", "excel", "数据分析", "数据清洗"]) skillDomains[name] = { domain: "data", label: "数据" };
for (const name of ["pytest", "单元测试", "软件测试"]) skillDomains[name] = { domain: "testing", label: "测试" };
for (const name of ["git", "linux", "docker", "kubernetes", "沟通", "团队协作"]) skillDomains[name] = { domain: "tools", label: "工具" };
const skillDomain = (name: string) => skillDomains[name.trim().toLowerCase()] ?? { domain: "tools", label: "工具与未知" };

export default function SkillPanorama() {
  const { user, status } = useAuth();
  return <AccessGate roles={["student"]}>{status === "authenticated" && user?.role === "student" &&
    <SkillPanoramaWorkspace key={`${user.id}:${user.role}`} ownerId={user.id} />}</AccessGate>;
}

export function SkillPanoramaWorkspace({ ownerId }: { ownerId: string }) {
  const [state, setState] = useState<PanoramaState>(initialPanoramaState);
  const [selected, setSelected] = useState<string | null>(null);
  const selectedByUser = useRef(false);
  const session = useMemo(() => createSkillPanoramaSession(ownerId, { listReports: api.listReports, getReport: api.getReport, errorMessage }, setState), [ownerId]);
  useEffect(() => {
    session.activate(); void session.loadMore();
    return () => session.dispose();
  }, [session]);
  useEffect(() => {
    if (selected !== null) { selectedByUser.current = true; return; }
    if (selectedByUser.current || !state.reports.length) return;
    const first = buildSkillPanorama(state.reports).skills[0];
    if (first) { selectedByUser.current = true; setSelected(first.key); }
  }, [state.reports, selected]);
  return <SkillPanoramaView state={state} selected={selected} onSelect={value => { selectedByUser.current = true; setSelected(value); }}
    loadMore={() => void session.loadMore()} retryFailed={() => void session.retryFailed()} />;
}

function CountBand({ counts, label }: { counts: StatusCounts; label: string }) {
  // Thin quantity band only: category color stays neutral, evidence status colors stay here.
  return <div className={styles.band} role="img" aria-label={`${label}：${PANORAMA_STATUSES.filter(status => counts[status]).map(status => `${PANORAMA_STATUS_LABELS[status]} ${counts[status]} 条`).join("，")}`}>
    {PANORAMA_STATUSES.filter(status => counts[status] > 0).map(status => <span key={status} data-status={status}
      style={{ flexGrow: counts[status] }} title={`${PANORAMA_STATUS_LABELS[status]} · ${counts[status]} 条`} />)}
  </div>;
}

function ContextRecord({ context }: { context: SkillContext }) {
  const { item } = context;
  return <article className={styles.context}>
    <div className={styles.contextMeta}><span data-status={panoramaStatus(item.verdict)}>{PANORAMA_STATUS_LABELS[panoramaStatus(item.verdict)]}</span>
      {context.isLatestForJob !== undefined && <span>{context.isLatestForJob ? "该岗位最新报告" : "历史报告"}</span>}
      <time dateTime={context.createdAt}>{new Date(context.createdAt).toLocaleDateString("zh-CN")}</time></div>
    <h3>{displayJobTitle(context.jobTitle, context.jobId)}</h3>
    <p className={styles.requirement}>{item.requirementTitle}</p>
    {panoramaStatus(item.verdict) === "unknown" && <p className={styles.date}>原始状态：{item.verdict || "未提供"}</p>}
    {item.confirmationStatus && item.confirmationStatus !== "pending" && <p className={styles.date}>本人核对：{{ accepted: "已采纳", rejected: "已驳回，需复核", corrected: "已标记修正，需复核" }[item.confirmationStatus]}</p>}
    {context.materials.length > 0 && <p className={styles.materials}>{context.materials.map(material =>
      `${displayMaterialTitle(material.title, material.id)} v${material.versionNumber}${material.materialRole === "reference" ? "（参考）" : ""}`).join(" · ")}</p>}
    <Link className={styles.reportLink} href={`/reports/${encodeURIComponent(context.reportId)}#requirement-${encodeURIComponent(item.requirementId)}`}>核对原报告这项要求 <span aria-hidden="true">↗</span></Link>
  </article>;
}

export function SkillPanoramaView({ state, selected, onSelect, loadMore, retryFailed }: {
  state: PanoramaState; selected: string | null; onSelect(key: string | null): void; loadMore(): void; retryFailed(): void;
}) {
  const reports = state.summaries.flatMap(summary => state.reports.filter(report => report.id === summary.id));
  const landscape = buildSkillPanorama(reports);
  const skill = landscape.skills.find(value => value.key === selected);
  const contexts = selected === "" ? landscape.unclassified : skill?.contexts;
  const failed = Object.keys(state.failures).length;
  const empty = !state.busy && state.total === 0;
  // Empty categories are filtered out before numbering, so group numbers stay continuous (01, 02, 03…).
  const groups = PANORAMA_CATEGORIES
    .map(category => ({ category, skills: landscape.skills.filter(value => value.category === category) }))
    .filter(group => group.skills.length > 0);
  return <div className={styles.panorama}>
    <header className={styles.heading}>
      <div><h1>技能全景</h1><p className={styles.subtitle}>汇总已保存报告中的技能与材料支持记录。</p></div>
      <Link href="/reports" className={styles.back}>← 我的报告</Link>
    </header>
    <div className={styles.loadbar} role="status" aria-live="polite">
      <p>{state.busy ? "正在分批读取报告…" : <>已读取 <strong>{state.reports.length}</strong>{state.total !== null && <> / {state.total}</>} 份报告</>}
        {failed > 0 && <> · <span className={styles.failureText}>{failed} 份详情失败</span></>}</p>
      {state.hasMore && !state.busy && <button className="btn-secondary btn-compact" disabled={state.busy} onClick={loadMore}>再加载最多 {PANORAMA_PAGE_SIZE} 份报告</button>}
    </div>
    {state.listError && <div role="alert" className={styles.error}><p>报告列表读取失败：{state.listError}</p>{!state.blocked && <button className="btn-secondary" disabled={state.busy} onClick={loadMore}>重试列表读取</button>}</div>}
    {failed > 0 && <details className={styles.failures}><summary>{failed} 份报告详情暂不可用，已读取内容仍保留</summary><ul>{state.summaries.filter(report => state.failures[report.id]).map(report => <li key={report.id}>{displayJobTitle(report.jobTitle, report.jobId)} · {new Date(report.createdAt).toLocaleString("zh-CN")}：{state.failures[report.id]}</li>)}</ul>
      <button className="btn-secondary" disabled={state.busy} onClick={retryFailed}>仅重试失败详情</button></details>}
    {empty ? <section className={styles.empty}><p className={styles.eyebrow}>从第一份报告开始</p><h2>还没有已保存报告</h2><p>选择岗位，用已有材料生成报告后，这里会整理报告中明确记录的技能。</p><Link href="/jobs" className="btn">选择岗位</Link></section> : <div className={styles.layout}>
      <section className={styles.canvas} aria-label="技能分组全景" aria-busy={state.busy}>
        <div className={styles.canvasTitle}><h2>技能版图</h2><p><strong>{landscape.skills.length}</strong> 个技能 · <strong>{landscape.contextCount}</strong> 条要求记录</p></div>
        <div className={styles.legend}>
          <ul>{PANORAMA_STATUSES.map(status => <li key={status}><i data-status={status} aria-hidden="true" />{PANORAMA_STATUS_LABELS[status]}{landscape.counts[status] > 0 && <strong>{landscape.counts[status]}</strong>}</li>)}</ul></div>
        {groups.map((group, index) => {
          const counts = group.skills.reduce((counts, value) => {
            for (const status of PANORAMA_STATUSES) counts[status] += value.counts[status];
            return counts;
          }, Object.fromEntries(PANORAMA_STATUSES.map(status => [status, 0])) as StatusCounts);
          return <section className={styles.group} key={group.category} aria-label={group.category}>
            <div className={styles.groupHeading}><span className={styles.groupNumber}>{String(index + 1).padStart(2, "0")}</span><h3>{group.category}</h3><span>{group.skills.length} 技能 · {group.skills.reduce((total, value) => total + value.contexts.length, 0)} 条</span></div>
            <CountBand counts={counts} label={group.category} />
            <div className={styles.skills}>{group.skills.map(value => { const domain = skillDomain(value.name); return <button key={value.key} className={styles.skill} aria-pressed={selected === value.key} aria-controls="skill-context-rail" onClick={() => onSelect(value.key)}>
              <span>{value.name}</span><span className={styles.skillDomain} data-domain={domain.domain}>{domain.label}</span><span className={styles.skillCount}>{value.contexts.length}<span className="sr-only"> 条要求记录</span></span>
              <span className={styles.skillMarks} aria-hidden="true">{PANORAMA_STATUSES.filter(status => value.counts[status]).map(status => <i key={status} data-status={status} />)}</span>
            </button>; })}</div>
          </section>;
        })}
        {!!landscape.unclassified.length && <button className={styles.unclassified} aria-pressed={selected === ""} aria-controls="skill-context-rail" onClick={() => onSelect("")}>未标注技能的要求 <strong>{landscape.unclassified.length}</strong><span>保留原要求，不推测技能名称 →</span></button>}
        {!landscape.contextCount && <p className={styles.noRecords}>{state.busy ? "正在读取报告中的技能与要求…" : "已读取报告中暂无技能或要求记录。可核对原报告，或继续加载其他报告。"}</p>}
      </section>
      <aside className={styles.rail} id="skill-context-rail" aria-label="所选技能的岗位语境">
        {contexts ? <><div className={styles.railHeading}><p className={styles.eyebrow}>岗位语境</p><h2>{skill?.name ?? "未标注技能的要求"}</h2><p>{contexts.length} 条要求 · {new Set(contexts.map(context => context.jobId)).size} 个岗位</p><button onClick={() => onSelect(null)} className={styles.reportLink}>返回读取概览</button></div>
          {contexts.map(context => <ContextRecord key={context.key} context={context} />)}</> : <div className={styles.railHeading}><p className={styles.eyebrow}>岗位语境</p><h2>选择一个技能</h2><p>点击左侧技能，逐条核对岗位要求、证据状态和报告固定版本。</p></div>}
      </aside>
    </div>}
  </div>;
}

