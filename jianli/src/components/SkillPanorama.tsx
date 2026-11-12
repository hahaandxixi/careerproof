"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import {
  buildSkillPanorama, createSkillPanoramaSession, filterSkillContexts, groupContextsByJob, initialPanoramaState,
  PANORAMA_CATEGORIES, PANORAMA_FILTERS, PANORAMA_FILTER_LABELS, PANORAMA_PAGE_SIZE, PANORAMA_STATUSES,
  PANORAMA_STATUS_LABELS, panoramaStatus, selectionForFilter, skillJobCount,
  type PanoramaFilter, type PanoramaState, type SkillContext, type StatusCounts,
} from "@/lib/skill-panorama";
import AccessGate from "./AccessGate";
import EvidenceSnippet from "./EvidenceSnippet";
import SourceIdentity from "./SourceIdentity";
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
  const [filter, setFilter] = useState<PanoramaFilter>("all");
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
  // Switching the status filter must not leave a hidden skill selected with an
  // empty rail. Keep the current skill when it still matches, otherwise move to
  // the first skill that has a matching saved record.
  const chooseFilter = (next: PanoramaFilter) => {
    setFilter(next);
    if (selected === null) return;
    setSelected(selectionForFilter(buildSkillPanorama(state.reports), selected, next));
  };
  return <SkillPanoramaView state={state} selected={selected} filter={filter} onFilterChange={chooseFilter}
    onSelect={value => { selectedByUser.current = true; setSelected(value); }}
    loadMore={() => void session.loadMore()} refresh={() => { setSelected(null); selectedByUser.current = false; void session.refresh(); }} retryFailed={() => void session.retryFailed()} />;
}

/** Quantity band inside one skill card. Status colors never leak onto the domain tag. */
function CountBand({ counts, label }: { counts: StatusCounts; label: string }) {
  return <div className={styles.band} role="img" aria-label={`${label}：${PANORAMA_STATUSES.filter(status => counts[status]).map(status => `${PANORAMA_STATUS_LABELS[status]} ${counts[status]} 条`).join("，")}`}>
    {PANORAMA_STATUSES.filter(status => counts[status] > 0).map(status => <span key={status} data-status={status}
      style={{ flexGrow: counts[status] }} title={`${PANORAMA_STATUS_LABELS[status]} · ${counts[status]} 条`} />)}
  </div>;
}

/** Small technical glyphs keep cards scannable without inventing capability levels. */
function SkillIcon({ domain }: { domain: string }) {
  const paths: Record<string, ReactNode> = {
    backend: <><path d="M8 7 3 12l5 5" /><path d="m16 7 5 5-5 5" /><path d="m13.5 5-3 14" /></>,
    data: <><ellipse cx="12" cy="5.5" rx="7" ry="3" /><path d="M5 5.5v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /><path d="M5 11.5v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></>,
    testing: <><path d="M9 3h6" /><path d="M10 3v6l-5 8.5A2.2 2.2 0 0 0 6.9 21h10.2a2.2 2.2 0 0 0 1.9-3.5L14 9V3" /><path d="M7.5 16h9" /></>,
    frontend: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 8h18" /><path d="m9 12 2 2-2 2" /><path d="m15 12-2 2 2 2" /></>,
    tools: <><path d="M14.7 6.3a4 4 0 0 0-5-5L12 3.6 9.4 6.2 7.1 3.9a4 4 0 0 0 5 5L21 18l-3 3-9.1-9.1" /></>,
  };
  return <span className={styles.skillIcon} data-domain={domain} aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[domain] ?? paths.tools}</svg></span>;
}

function ContextRecord({ context, active, onSelect }: { context: SkillContext; active: boolean; onSelect(key: string): void }) {
  const { item } = context;
  const evidenceList = item.evidenceList ?? [];
  const reportHref = `/reports/${encodeURIComponent(context.reportId)}#requirement-${encodeURIComponent(item.requirementId)}`;
  return <article className={`${styles.context} ${active ? styles.contextActive : ""}`}>
    <button type="button" className={styles.contextSelect} aria-pressed={active} onClick={() => onSelect(context.key)}>
      <span className={styles.contextMeta}>
        <span data-status={panoramaStatus(item.verdict)}>原报告 · {PANORAMA_STATUS_LABELS[panoramaStatus(item.verdict)]}</span>
        {context.isLatestForJob === true && <span>该岗位最新报告</span>}
        <time dateTime={context.createdAt}>{new Date(context.createdAt).toLocaleDateString("zh-CN")}</time>
      </span>
      <span className={styles.requirement}>{item.requirementTitle}</span>
      {panoramaStatus(item.verdict) === "unknown" && <span className={styles.date}>原始状态：{item.verdict || "未提供"}</span>}
      {item.confirmationStatus && item.confirmationStatus !== "pending" && <span className={styles.date}>本人核对：{{ accepted: "已采纳", rejected: "已驳回，需复核", corrected: "已标记修正，需复核" }[item.confirmationStatus]}</span>}
      {context.materials.length > 0 && <span className={styles.materials}>{context.materials.map(material =>
        `${displayMaterialTitle(material.title, material.id)} v${material.versionNumber}${material.materialRole === "reference" ? "（参考）" : ""}`).join(" · ")}</span>}
    </button>
    <Link className={styles.reportLink} href={reportHref}>核对原报告这项要求 <span aria-hidden="true">↗</span></Link>
    {active && <section className={styles.contextSource} aria-label="当前记录的引用与材料">
      <h4>判断与引用材料</h4>
      <p className={styles.sourceScope}>{displayJobTitle(context.jobTitle, context.jobId)} · {new Date(context.createdAt).toLocaleString("zh-CN")} · 固定材料 {context.materials.length ? `v${context.materials[0].versionNumber} 起 ${context.materials.length} 份` : "未记录"}</p>
      {evidenceList.length ? evidenceList.map((evidence, index) => <div key={`${evidence.citationId}:${index}`} className={styles.contextEvidence}>
        <p><SourceIdentity source={evidence} materials={context.materials} compact/> · 第 {evidence.lineStart}–{evidence.lineEnd} 行</p>
        <EvidenceSnippet evidence={evidence} materials={context.materials} showContextNote={false} theme="dark"/>
      </div>) : <p className={styles.contextNoSource}>{item.verdict === "unsupported" ? "此项暂未评估，请核对岗位要求与材料。" : item.verdict === "claimed_only" ? "暂无此项要求的可定位引用；目前仅见简历声明。" : item.verdict === "gap" ? "暂无此项要求的可定位引用；这是材料缺口。" : "暂无此项要求的可定位引用。"}</p>}
    </section>}
  </article>;
}

function SkillContextRail({ contexts, skillName, filter, matched, total, onClear }: {
  contexts: SkillContext[]; skillName: string; filter: PanoramaFilter; matched: number; total: number; onClear(): void;
}) {
  const [pickedContext, setPickedContext] = useState<string | null>(null);
  const groups = groupContextsByJob(contexts);
  const activeKey = contexts.some(context => context.key === pickedContext) ? pickedContext : contexts[0]?.key ?? null;
  const jobs = new Set(contexts.map(context => context.jobId)).size;
  return <>
    <div className={styles.railHeading}>
      <h2>{skillName}</h2>
      <p>{filter === "all" ? <>{total} 条要求记录 · {jobs} 个岗位</> : <>命中 <strong>{matched}</strong> 条 / 共 {total} 条 · {jobs} 个岗位</>}</p>
      <button onClick={onClear} className={styles.clearSelection}>清除选择</button>
    </div>
    {!contexts.length && <p className={styles.contextNoSource}>当前筛选下，这项技能没有匹配的要求记录。切换筛选可恢复该技能的全部岗位历史。</p>}
    {groups.map(group => {
      const byReport = new Map<string, SkillContext[]>();
      for (const context of group.contexts) {
        const records = byReport.get(context.reportId);
        if (records) records.push(context);
        else byReport.set(context.reportId, [context]);
      }
      const [primary, ...rest] = [...byReport.values()];
      const renderRecords = (records: SkillContext[]) => records.map(context =>
        <ContextRecord key={context.key} context={context} active={activeKey === context.key} onSelect={setPickedContext}/>,
      );
      return <section key={group.jobId} className={styles.jobGroup} aria-label={`${displayJobTitle(group.jobTitle, group.jobId)} 的报告要求`}>
        <header className={styles.jobHeading}>
          <span className={styles.contextJob}>{displayJobTitle(group.jobTitle, group.jobId)}</span>
          <span className={styles.jobMeta}>{byReport.size} 份报告 · {group.contexts.length} 条要求</span>
        </header>
        {renderRecords(primary)}
        {!!rest.length && <details className={styles.history}>
          <summary>该岗位其他 {rest.length} 份历史报告</summary>
          {rest.map(records => <div key={records[0].reportId}>{renderRecords(records)}</div>)}
        </details>}
      </section>;
    })}
  </>;
}

export function SkillPanoramaView({ state, selected, filter = "all", onSelect, onFilterChange, loadMore, refresh, retryFailed }: {
  state: PanoramaState; selected: string | null; filter?: PanoramaFilter;
  onSelect(key: string | null): void; onFilterChange?(filter: PanoramaFilter): void; loadMore(): void; refresh?(): void; retryFailed(): void;
}) {
  const reports = state.summaries.flatMap(summary => state.reports.filter(report => report.id === summary.id));
  const landscape = buildSkillPanorama(reports);
  const skill = landscape.skills.find(value => value.key === selected);
  const allContexts = selected === "" ? landscape.unclassified : skill?.contexts ?? [];
  const matchedContexts = filterSkillContexts(allContexts, filter);
  const failed = Object.keys(state.failures).length;
  const empty = !state.busy && state.total === 0;
  // A skill stays visible when any saved record matches; its own card keeps every
  // original status, so the same skill can match more than one filter.
  const visibleSkills = landscape.skills.filter(value => filterSkillContexts(value.contexts, filter).length > 0);
  const unclassifiedMatched = filterSkillContexts(landscape.unclassified, filter).length;
  const groups = PANORAMA_CATEGORIES
    .map(category => ({ category, skills: visibleSkills.filter(value => value.category === category) }))
    .filter(group => group.skills.length > 0);
  const filterCount = (value: PanoramaFilter) => filterSkillContexts(
    [...landscape.skills.flatMap(entry => entry.contexts), ...landscape.unclassified], value).length;
  return <div className={styles.panorama}>
    <header className={styles.heading}>
      <div><h1>技能全景</h1><p className={styles.subtitle}>汇总已保存报告中的技能与材料支持记录，按岗位逐条核对原始要求。</p></div>
      <p className={styles.headMeta}><strong>{landscape.skills.length}</strong> 个技能 · <strong>{landscape.contextCount}</strong> 条要求记录</p>
    </header>
    <div className={styles.loadbar} role="status" aria-live="polite">
      <p>{state.busy ? "正在分批读取报告…" : <>已读取 <strong>{state.reports.length}</strong>{state.total !== null && <> / {state.total}</>} 份报告</>}
        {failed > 0 && <> · <span className={styles.failureText}>{failed} 份详情失败</span></>}</p>
      {state.hasMore && !state.busy && <button className="btn-secondary btn-compact" disabled={state.busy} onClick={loadMore}>再加载最多 {PANORAMA_PAGE_SIZE} 份报告</button>}
      {!state.hasMore && state.total !== null && state.summaries.length !== state.total && !state.blocked && <div>
        <p>列表有更新。已读记录与当前总数不同，可从第一页重新读取。</p>
        {refresh && <button className="btn-secondary btn-compact" disabled={state.busy} onClick={refresh}>重新读取报告列表</button>}
      </div>}
    </div>
    {state.listError && <div role="alert" className={styles.error}><p>报告列表读取失败：{state.listError}</p>{!state.blocked && <button className="btn-secondary" disabled={state.busy} onClick={loadMore}>重试列表读取</button>}</div>}
    {failed > 0 && <details className={styles.failures}><summary>{failed} 份报告详情暂不可用，已读取内容仍保留</summary><ul>{state.summaries.filter(report => state.failures[report.id]).map(report => <li key={report.id}>{displayJobTitle(report.jobTitle, report.jobId)} · {new Date(report.createdAt).toLocaleString("zh-CN")}：{state.failures[report.id]}</li>)}</ul>
      <button className="btn-secondary" disabled={state.busy} onClick={retryFailed}>仅重试失败详情</button></details>}
    {empty ? <section className={styles.empty}><p className={styles.eyebrow}>从第一份报告开始</p><h2>还没有已保存报告</h2><p>选择岗位，用已有材料生成报告后，这里会整理报告中明确记录的技能。</p><Link href="/jobs" className="btn">选择岗位</Link></section> : <div className={styles.layout}>
      <section className={styles.canvas} aria-label="技能分组全景" aria-busy={state.busy}>
        <div className={styles.legend}>
          <ul>{PANORAMA_STATUSES.map(status => <li key={status}><i data-status={status} aria-hidden="true" />{PANORAMA_STATUS_LABELS[status]}{landscape.counts[status] > 0 && <strong>{landscape.counts[status]}</strong>}</li>)}</ul></div>
        <p className={styles.contextNoSource}>筛选和色带按原报告状态统计；本人复核单独标记。</p>
        <div className={styles.filters} role="group" aria-label="按原报告状态筛选">
          {PANORAMA_FILTERS.map(value => <button key={value} type="button" aria-pressed={filter === value}
            onClick={() => onFilterChange?.(value)}>
            {PANORAMA_FILTER_LABELS[value]} <span>{filterCount(value)}</span>
          </button>)}
        </div>
        {groups.map((group, index) => {
          return <section className={styles.group} key={group.category} aria-label={group.category}>
            <div className={styles.groupHeading}><span className={styles.groupNumber}>{String(index + 1).padStart(2, "0")}</span><h3>{group.category}</h3><span>{group.skills.length} 技能 · {group.skills.reduce((total, value) => total + filterSkillContexts(value.contexts, filter).length, 0)} 条</span></div>
            <div className={styles.skills}>{group.skills.map(value => {
              const domain = skillDomain(value.name);
              const matched = filterSkillContexts(value.contexts, filter).length;
              const selectedCard = selected === value.key;
              return <button key={value.key} className={styles.skillCard} aria-pressed={selectedCard} aria-controls="skill-context-rail" onClick={() => onSelect(value.key)}>
                <SkillIcon domain={domain.domain}/>
                <span className={styles.skillCardBody}>
                  <span className={styles.skillCardTop}><span className={styles.skillName}>{value.name}</span><span className={styles.skillDomain} data-domain={domain.domain}>{domain.label}</span></span>
                  <CountBand counts={value.counts} label={value.name}/>
                  <span className={styles.skillCounts}>{PANORAMA_STATUSES.filter(status => value.counts[status] > 0).map(status =>
                    <span key={status} data-status={status}>{PANORAMA_STATUS_LABELS[status]} {value.counts[status]} 条</span>)}</span>
                  <span className={styles.skillFooter}>
                    <span>{value.contexts.length} 条要求记录</span>
                    {value.contexts.some(({ item }) => item.confirmationStatus === "rejected" || item.confirmationStatus === "corrected") && <span>需复核 {value.contexts.filter(({ item }) => item.confirmationStatus === "rejected" || item.confirmationStatus === "corrected").length} 条</span>}
                    <span>{skillJobCount(value.contexts)} 个岗位</span>
                    {filter !== "all" && <span className={styles.hit}>命中 {matched} 条</span>}
                  </span>
                </span>
                <span className={styles.cardArrow} aria-hidden="true">{selectedCard ? "已选" : "查看 →"}</span>
              </button>;
            })}</div>
          </section>;
        })}
        {!!unclassifiedMatched && <button className={styles.unclassified} aria-pressed={selected === ""} aria-controls="skill-context-rail" onClick={() => onSelect("")}>未标注技能的要求 <strong>{unclassifiedMatched}</strong><span>保留原要求，不推测技能名称 →</span></button>}
        {!landscape.contextCount && <p className={styles.noRecords}>{state.busy ? "正在读取报告中的技能与要求…" : "已读取报告中暂无技能或要求记录。可核对原报告，或继续加载其他报告。"}</p>}
        {!!landscape.contextCount && !visibleSkills.length && !unclassifiedMatched && <p className={styles.noRecords}>当前筛选没有匹配的要求记录。<button type="button" className="btn-secondary btn-compact" onClick={() => onFilterChange?.("all")}>查看全部记录</button></p>}
      </section>
      <aside className={styles.rail} id="skill-context-rail" aria-label="所选技能的岗位语境">
        {selected === "" || skill ? <SkillContextRail contexts={matchedContexts} skillName={selected === "" ? "未标注技能的要求" : skill!.name}
          filter={filter} matched={matchedContexts.length} total={allContexts.length} onClear={() => onSelect(null)}/> :
          <div className={styles.railHeading}><p className={styles.eyebrow}>岗位语境</p><h2>选择一个技能</h2><p>点击左侧技能卡，按岗位核对报告要求、当前判断、固定材料版本与引用。</p></div>}
      </aside>
    </div>}
  </div>;
}
