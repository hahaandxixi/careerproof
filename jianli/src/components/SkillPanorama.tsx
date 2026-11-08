"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { demoJobAlias, displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import {
  buildSkillPanorama, createSkillPanoramaSession, initialPanoramaState,
  PANORAMA_CATEGORIES, PANORAMA_PAGE_SIZE, PANORAMA_STATUSES, PANORAMA_STATUS_LABELS, panoramaStatus,
  type PanoramaState, type SkillContext, type StatusCounts,
} from "@/lib/skill-panorama";
import AccessGate from "./AccessGate";
import { useAuth } from "./AuthProvider";
import styles from "./SkillPanorama.module.css";

export default function SkillPanorama() {
  const { user, status } = useAuth();
  return <AccessGate roles={["student"]}>{status === "authenticated" && user?.role === "student" &&
    <SkillPanoramaWorkspace key={`${user.id}:${user.role}`} ownerId={user.id} />}</AccessGate>;
}

export function SkillPanoramaWorkspace({ ownerId }: { ownerId: string }) {
  const [state, setState] = useState<PanoramaState>(initialPanoramaState);
  const [selected, setSelected] = useState<string | null>(null);
  const session = useMemo(() => createSkillPanoramaSession(ownerId, { listReports: api.listReports, getReport: api.getReport, errorMessage }, setState), [ownerId]);
  useEffect(() => {
    session.activate(); void session.loadMore();
    return () => session.dispose();
  }, [session]);
  return <SkillPanoramaView state={state} selected={selected} onSelect={setSelected}
    loadMore={() => void session.loadMore()} retryFailed={() => void session.retryFailed()} />;
}

function CountBand({ counts, label }: { counts: StatusCounts; label: string }) {
  return <div className={styles.band} role="img" aria-label={`${label}：${PANORAMA_STATUSES.filter(status => counts[status]).map(status => `${PANORAMA_STATUS_LABELS[status]} ${counts[status]} 条`).join("，")}`}>
    {PANORAMA_STATUSES.filter(status => counts[status] > 0).map(status => <span key={status} data-status={status}
      style={{ flexGrow: counts[status] }} title={`${PANORAMA_STATUS_LABELS[status]} · ${counts[status]} 条`}>{counts[status]}</span>)}
  </div>;
}

function ContextRecord({ context }: { context: SkillContext }) {
  const { item } = context;
  return <article className={styles.context}>
    <div className={styles.contextMeta}><span data-status={panoramaStatus(item.verdict)}>{PANORAMA_STATUS_LABELS[panoramaStatus(item.verdict)]}</span>
      {context.isLatestForJob !== undefined && <span>{context.isLatestForJob ? "该岗位最新报告" : "历史报告"}</span>}</div>
    <h3>{displayJobTitle(context.jobTitle, context.jobId)}</h3>
    <p className={styles.requirement}>{item.requirementTitle}</p>
    <p className={styles.date}>{new Date(context.createdAt).toLocaleString("zh-CN")}</p>
    {panoramaStatus(item.verdict) === "unknown" && <p className={styles.date}>原始状态：{item.verdict || "未提供"}</p>}
    {item.confirmationStatus && <p className={styles.date}>本人核对：{{ pending: "待核对", accepted: "已采纳", rejected: "已驳回，需复核", corrected: "已标记修正，需复核" }[item.confirmationStatus]}</p>}
    <div className={styles.materials}><p>报告固定材料</p>{context.materials.length ? <ul>{context.materials.map(material =>
      <li key={`${material.kind}:${material.id}:${material.versionNumber}`}>{displayMaterialTitle(material.title, material.id)} <strong>v{material.versionNumber}</strong>{material.materialRole === "reference" && " · 参考材料"}</li>)}</ul> : <p>本报告未记录固定材料。</p>}</div>
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
  const remaining = state.total === null ? null : Math.max(0, state.total - state.summaries.length);
  const pending = Math.max(0, state.summaries.length - state.reports.length - failed);
  const empty = !state.busy && state.total === 0;
  return <div className={styles.panorama}>
    <Link href="/reports" className={styles.back}>← 我的报告</Link>
    <header className={styles.heading}><div><h1>技能全景</h1>
      <p className={styles.subtitle}>汇总已保存报告中的技能与材料支持记录。</p></div></header>
    {reports.some(report => demoJobAlias(report.jobId)) && <p className="text-sm text-slate-600">演示数据说明：示例岗位、企业与材料均为虚构，不代表真实招聘或能力认证。</p>}
    <div className={styles.loadbar} role="status" aria-live="polite">
      <p>已读取 <strong>{state.reports.length}</strong> 份详情 / <strong>{state.summaries.length}</strong> 份摘要{state.total !== null && <> · 共 {state.total} 份报告</>}
        {pending > 0 && <> · {pending} 份详情待读取</>}{failed > 0 && <> · <span className={styles.failureText}>{failed} 份详情失败</span></>}
        {remaining !== null && <> · {remaining} 份摘要未加载</>}</p>
      <span>{state.busy ? "正在分批读取…" : "含历史报告 · 不合并跨岗位结论"}</span>
    </div>
    {state.listError && <div role="alert" className={styles.error}><p>报告列表读取失败：{state.listError}</p>{!state.blocked && <button className="btn-secondary" disabled={state.busy} onClick={loadMore}>重试列表读取</button>}</div>}
    {failed > 0 && <details className={styles.failures}><summary>{failed} 份报告详情暂不可用，已读取内容仍保留</summary><ul>{state.summaries.filter(report => state.failures[report.id]).map(report => <li key={report.id}>{displayJobTitle(report.jobTitle, report.jobId)} · {new Date(report.createdAt).toLocaleString("zh-CN")}：{state.failures[report.id]}</li>)}</ul>
      <button className="btn-secondary" disabled={state.busy} onClick={retryFailed}>仅重试失败详情</button></details>}
    {empty ? <section className={styles.empty}><p className={styles.eyebrow}>从第一份报告开始</p><h2>还没有已保存报告</h2><p>选择岗位，用已有材料生成报告后，这里会整理报告中明确记录的技能。</p><Link href="/jobs" className="btn">选择岗位</Link></section> : <div className={styles.layout}>
      <section className={styles.canvas} aria-label="技能分组全景" aria-busy={state.busy}>
        <div className={styles.canvasTitle}><h2>技能版图</h2><p><strong>{landscape.skills.length}</strong> 个技能 · <strong>{landscape.contextCount}</strong> 条要求记录</p></div>
        <div className={styles.legend}><p>色带按要求记录计数，不代表技能熟练度；同一技能可有不同结论。</p>
          <ul>{PANORAMA_STATUSES.map(status => <li key={status}><i data-status={status} aria-hidden="true" />{PANORAMA_STATUS_LABELS[status]}{landscape.counts[status] > 0 && <strong>{landscape.counts[status]}</strong>}</li>)}</ul></div>
        {PANORAMA_CATEGORIES.map((category, index) => {
          const skills = landscape.skills.filter(value => value.category === category);
          if (!skills.length) return null;
          const counts = skills.reduce((counts, value) => {
            for (const status of PANORAMA_STATUSES) counts[status] += value.counts[status];
            return counts;
          }, Object.fromEntries(PANORAMA_STATUSES.map(status => [status, 0])) as StatusCounts);
          return <section className={styles.group} key={category} aria-label={category}>
            <div className={styles.groupHeading}><span className={styles.groupNumber}>{String(index + 1).padStart(2, "0")}</span><h3>{category}</h3><span>{skills.length} 个技能 · {skills.reduce((total, value) => total + value.contexts.length, 0)} 条记录</span></div>
            <CountBand counts={counts} label={category} />
            <div className={styles.skills}>{skills.map(value => <button key={value.key} className={styles.skill} aria-pressed={selected === value.key} aria-controls="skill-context-rail" onClick={() => onSelect(value.key)}>
              <span>{value.name}</span><span className={styles.skillCount}>{value.contexts.length}<span className="sr-only"> 条要求记录</span></span>
              <span className={styles.skillMarks} aria-hidden="true">{PANORAMA_STATUSES.filter(status => value.counts[status]).map(status => <i key={status} data-status={status} />)}</span>
            </button>)}</div>
          </section>;
        })}
        {!!landscape.unclassified.length && <button className={styles.unclassified} aria-pressed={selected === ""} aria-controls="skill-context-rail" onClick={() => onSelect("")}>未标注技能的要求 <strong>{landscape.unclassified.length}</strong><span>保留原要求，不推测技能名称 →</span></button>}
        {!landscape.contextCount && <p className={styles.noRecords}>{state.busy ? "正在读取报告中的技能与要求…" : "已读取报告中暂无技能或要求记录。可核对原报告，或继续加载其他报告。"}</p>}
        <div className={styles.canvasFooter}><p>分组仅用于浏览；未识别的名称保留在「其他 / 未分类」。</p>
          {state.hasMore && <button className="btn-secondary" disabled={state.busy} onClick={loadMore}>{state.busy ? "正在读取…" : `再加载最多 ${PANORAMA_PAGE_SIZE} 份报告`}</button>}</div>
      </section>
      <aside className={styles.rail} id="skill-context-rail" aria-label="所选技能的岗位语境">
        {contexts ? <><div className={styles.railHeading}><p className={styles.eyebrow}>岗位语境</p><h2>{skill?.name ?? "未标注技能的要求"}</h2><p>{contexts.length} 条要求 · {new Set(contexts.map(context => context.jobId)).size} 个岗位</p><button onClick={() => onSelect(null)} className={styles.reportLink}>返回读取概览</button></div>
          <p className={styles.railNote}>每条结论只对应当时的岗位要求与固定材料。</p>
          {contexts.map(context => <ContextRecord key={context.key} context={context} />)}</> : <><div className={styles.railHeading}><p className={styles.eyebrow}>从技能，回到证据</p><h2>同一技能，不止一种语境</h2><p>点击左侧技能，逐条核对岗位要求、证据状态和报告固定版本。</p></div>
          <div className={styles.readingScope}><h3>本次已读取</h3><p>首批最多 {PANORAMA_PAGE_SIZE} 份，更多历史由你选择加载。</p>
            <ul>{reports.slice(0, 4).map(report => <li key={report.id}><Link href={`/reports/${encodeURIComponent(report.id)}`}>{displayJobTitle(report.jobTitle, report.jobId)} ↗</Link><span>{new Date(report.createdAt).toLocaleDateString("zh-CN")}</span></li>)}</ul>
            {reports.length > 4 && <p>以及 {reports.length - 4} 份已读取报告</p>}
            <p className={styles.railNote}>报告之外的新材料，不属于这些固定快照。</p></div></>}
      </aside>
    </div>}
  </div>;
}
