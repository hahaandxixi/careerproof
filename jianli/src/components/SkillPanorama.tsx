"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import {
  buildSkillPanorama, createSkillPanoramaSession, filterSkillContexts, groupContextsByJob, initialPanoramaState,
  PANORAMA_CATEGORIES, PANORAMA_FILTERS, PANORAMA_FILTER_LABELS, PANORAMA_PAGE_SIZE, PANORAMA_STATUSES,
  PANORAMA_STATUS_LABELS, panoramaStatus, selectionForFilter, skillJobCount, skillRecordMeasure,
  type PanoramaFilter, type PanoramaState, type SkillContext, type StatusCounts,
} from "@/lib/skill-panorama";
import AccessGate from "./AccessGate";
import EvidenceSnippet from "./EvidenceSnippet";
import SourceIdentity from "./SourceIdentity";
import SkillOverviewRadar from "./SkillOverviewRadar";
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

function CountBand({ counts, label }: { counts: StatusCounts; label: string }) {
  return <span className={styles.band} role="img" aria-label={`${label}：${PANORAMA_STATUSES.filter(status => counts[status]).map(status => `${PANORAMA_STATUS_LABELS[status]} ${counts[status]} 条`).join("，")}`}>
    {PANORAMA_STATUSES.filter(status => counts[status] > 0).map(status => <span key={status} data-status={status}
      style={{ flexGrow: counts[status] }} title={`${PANORAMA_STATUS_LABELS[status]} · ${counts[status]} 条`} />)}
  </span>;
}

function SelectedContext({ context }: { context: SkillContext }) {
  const { item } = context;
  const evidenceList = item.evidenceList ?? [];
  return <section className={styles.contextSource} aria-label="当前记录的引用与材料">
    <p className={styles.sourceScope}>{displayJobTitle(context.jobTitle, context.jobId)} · {new Date(context.createdAt).toLocaleString("zh-CN")}{context.isLatestForJob === true && " · 该岗位最新报告"}</p>
    <h3 className={styles.selectedRequirement}>{item.requirementTitle}</h3>
    <p className={styles.contextMeta}><span data-status={panoramaStatus(item.verdict)}>原报告 · {PANORAMA_STATUS_LABELS[panoramaStatus(item.verdict)]}</span>
      {item.confirmationStatus && item.confirmationStatus !== "pending" && <strong className={styles.reviewMark}>本人核对：{{ accepted: "已采纳", rejected: "已驳回，需复核", corrected: "已标记修正，需复核" }[item.confirmationStatus]}</strong>}</p>
    {panoramaStatus(item.verdict) === "unknown" && <p className={styles.date}>原始状态：{item.verdict || "未提供"}</p>}
    {context.materials.length > 0 && <details className={styles.materials}><summary>固定材料</summary><p>{context.materials.map(material => `${displayMaterialTitle(material.title, material.id)} v${material.versionNumber}${material.materialRole === "reference" ? "（参考）" : ""}`).join(" · ")}</p></details>}
    {evidenceList.length ? evidenceList.map((evidence, index) => <div key={`${evidence.citationId}:${index}`} className={styles.contextEvidence}>
      <p><SourceIdentity source={evidence} materials={context.materials} compact/> · 第 {evidence.lineStart}–{evidence.lineEnd} 行</p>
      <EvidenceSnippet evidence={evidence} materials={context.materials} showContextNote={false} theme="dark"/>
      {evidence.contextComplete === false && <p className={styles.contextNoSource}>{evidence.contextNote || "来源上下文不完整，请核对原报告。"}</p>}
    </div>) : <p className={styles.contextNoSource}>{item.verdict === "unsupported" ? "此项暂未评估，请核对岗位要求与材料。" : item.verdict === "claimed_only" ? "暂无此项要求的可定位引用；目前仅见简历声明。" : item.verdict === "gap" ? "暂无此项要求的可定位引用；这是材料缺口。" : "暂无此项要求的可定位引用。"}</p>}
    <Link className={styles.reportLink} href={`/reports/${encodeURIComponent(context.reportId)}#requirement-${encodeURIComponent(item.requirementId)}`}>核对原报告这项要求 <span aria-hidden="true">↗</span></Link>
  </section>;
}

function SkillContextRecords({ contexts, skillKey }: { contexts: SkillContext[]; skillKey: string }) {
  const [choices, setChoices] = useState<Record<string, string>>({});
  const groups = groupContextsByJob(contexts);
  const picked = contexts.find(context => context.key === choices[skillKey]);
  const active = picked ?? groups[0]?.contexts[0];
  if (!active) return <p className={styles.contextNoSource}>当前筛选下没有可查看的记录。</p>;
  const choose = (key: string) => setChoices(previous => ({ ...previous, [skillKey]: key }));
  return <>
    <div className={styles.drawerJobs} aria-label="按岗位查看记录">
      {groups.map(group => {
        const [first, ...history] = group.contexts;
        const jobSelected = active.jobId === group.jobId;
        const title = displayJobTitle(group.jobTitle, group.jobId);
        return <div key={group.jobId}>
          <button type="button" className="btn-secondary btn-compact" aria-pressed={jobSelected}
            onClick={() => choose(first.key)}>{title}</button>
          {jobSelected && history.length > 0 && <details className={styles.history}>
            <summary>同岗位其他记录（{history.length}）</summary>
            <ul>{history.map(context => <li key={context.key}>
              <button type="button" className={styles.recordButton} aria-pressed={active.key === context.key}
                onClick={() => choose(context.key)}>
                {new Date(context.createdAt).toLocaleString("zh-CN")} · {context.item.requirementTitle}
                {context.isLatestForJob === true && " · 该岗位最新报告"}
              </button>
            </li>)}</ul>
          </details>}
        </div>;
      })}
    </div>
    <SelectedContext context={active} />
  </>;
}

export function SkillPanoramaView({ state, selected, filter = "all", onSelect, onFilterChange, loadMore, refresh, retryFailed }: {
  state: PanoramaState; selected: string | null; filter?: PanoramaFilter;
  onSelect(key: string | null): void; onFilterChange?(filter: PanoramaFilter): void; loadMore(): void; refresh?(): void; retryFailed(): void;
}) {
  const reports = state.summaries.flatMap(summary => state.reports.filter(report => report.id === summary.id));
  const landscape = buildSkillPanorama(reports);
  const skill = landscape.skills.find(value => value.key === selected);
  const contexts = filterSkillContexts(selected === "" ? landscape.unclassified : skill?.contexts ?? [], filter);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const openEvidence = (key: string, trigger: HTMLButtonElement) => {
    onSelect(key);
    if (!dialog.current?.open && dialog.current) {
      opener.current = trigger;
      dialog.current.showModal();
    }
  };
  const restoreFocus = () => {
    if (opener.current?.isConnected) {
      opener.current.focus({ preventScroll: true });
    }
  };
  const failed = Object.keys(state.failures).length;
  const empty = !state.busy && state.total === 0;
  // A skill stays visible when any saved record matches; its own card keeps every
  // original status, so the same skill can match more than one filter.
  const visibleSkills = landscape.skills.filter(value => filterSkillContexts(value.contexts, filter).length > 0);
  const assessed = visibleSkills.filter(value => skillRecordMeasure(value).ratio !== null);
  const unassessed = visibleSkills.filter(value => skillRecordMeasure(value).ratio === null);
  const unclassifiedMatched = filterSkillContexts(landscape.unclassified, filter).length;
  const groups = PANORAMA_CATEGORIES
    .map(category => ({ category, skills: assessed.filter(value => value.category === category) }))
    .filter(group => group.skills.length > 0);
  const filterCount = (value: PanoramaFilter) => filterSkillContexts(
    [...landscape.skills.flatMap(entry => entry.contexts), ...landscape.unclassified], value).length;
  const listChanged = !state.hasMore && state.total !== null && state.summaries.length !== state.total && !state.blocked;
  return <div className={styles.panorama}>
    <header className={styles.heading}>
      <h1>技能全景</h1>
    </header>
    {(state.busy || state.hasMore || listChanged) && <div className={styles.loadbar} role="status" aria-live="polite">
      {state.busy ? <p>正在读取报告…</p> : state.hasMore && state.total !== null && <p>已读取 {state.reports.length} / {state.total} 份报告</p>}
      {state.hasMore && !state.busy && <button className="btn-secondary btn-compact" disabled={state.busy} onClick={loadMore}>再加载最多 {PANORAMA_PAGE_SIZE} 份报告</button>}
      {listChanged && <div>
        <p>列表有更新。已读记录与当前总数不同，可从第一页重新读取。</p>
        {refresh && <button className="btn-secondary btn-compact" disabled={state.busy} onClick={refresh}>重新读取报告列表</button>}
      </div>}
    </div>}
    {state.listError && <div role="alert" className={styles.error}><p>报告列表读取失败：{state.listError}</p>{!state.blocked && <button className="btn-secondary" disabled={state.busy} onClick={loadMore}>重试列表读取</button>}</div>}
    {failed > 0 && <details className={styles.failures}><summary>{failed} 份报告详情暂不可用，已读取内容仍保留</summary><ul>{state.summaries.filter(report => state.failures[report.id]).map(report => <li key={report.id}>{displayJobTitle(report.jobTitle, report.jobId)} · {new Date(report.createdAt).toLocaleString("zh-CN")}：{state.failures[report.id]}</li>)}</ul>
      <button className="btn-secondary" disabled={state.busy} onClick={retryFailed}>仅重试失败详情</button></details>}
    {empty ? <section className={styles.empty}><p className={styles.eyebrow}>从第一份报告开始</p><h2>还没有已保存报告</h2><p>选择岗位，用已有材料生成报告后，这里会整理报告中明确记录的技能。</p><Link href="/jobs" className="btn">选择岗位</Link></section> : <div className={styles.layout}>
      <section className={styles.canvas} aria-label="技能记录统计" aria-busy={state.busy}>
        <div className={styles.legend}>
          <ul aria-label="原报告状态图例">{PANORAMA_STATUSES.map(status => <li key={status}><i data-status={status} aria-hidden="true" />{PANORAMA_STATUS_LABELS[status]}</li>)}</ul></div>
        <div className={styles.filters} role="group" aria-label="按原报告状态筛选">
          {PANORAMA_FILTERS.map(value => <button key={value} type="button" aria-pressed={filter === value}
            onClick={() => onFilterChange?.(value)}>
            {PANORAMA_FILTER_LABELS[value]} <span>{filterCount(value)}</span>
          </button>)}
        </div>
        <SkillOverviewRadar skills={assessed} selected={selected} onSelect={onSelect} />
      </section>
      <section className={styles.cards} aria-label="技能分组全景">
        {groups.map(group => {
          return <section className={styles.group} key={group.category} aria-label={group.category} data-multiple={group.skills.length > 1 || undefined}>
            <div className={styles.groupHeading}><h3>{group.category}</h3></div>
            <div className={styles.skills}>{group.skills.map(value => {
              const reviewCount = value.contexts.filter(({ item }) => item.confirmationStatus === "rejected" || item.confirmationStatus === "corrected").length;
              const selectedCard = selected === value.key;
              return <div key={value.key} className={styles.skillCard} data-selected={selectedCard || undefined}>
                <button type="button" className={styles.skillCardSelect} aria-pressed={selectedCard} onClick={() => onSelect(value.key)}>
                  <span className={styles.skillCardBody}>
                    <span className={styles.skillName}>{value.name}</span>
                    <CountBand counts={value.counts} label={value.name}/>
                    <span className={styles.skillFooter}>
                      <span>{value.contexts.length} 条要求记录</span>
                      <span>{skillJobCount(value.contexts)} 个岗位</span>
                      {reviewCount > 0 && <span className={styles.reviewMark}>需复核 {reviewCount} 条</span>}
                    </span>
                  </span>
                </button>
                <button type="button" className={styles.cardEvidence} aria-haspopup="dialog" aria-controls="skill-evidence-drawer"
                  aria-label={"查看依据：" + value.name} onClick={event => openEvidence(value.key, event.currentTarget)}>查看依据 <span aria-hidden="true">→</span></button>
              </div>;
            })}</div>
          </section>;
        })}
        {!!unassessed.length && <details className={styles.unassessed}>
          <summary>未评估技能（{unassessed.length}）</summary>
          <ul>{unassessed.map(value => <li key={value.key}>
            <span>{value.name}</span>
            <button type="button" className={styles.cardEvidence} aria-haspopup="dialog" aria-controls="skill-evidence-drawer"
              aria-label={"查看依据：" + value.name} onClick={event => openEvidence(value.key, event.currentTarget)}>查看依据 <span aria-hidden="true">→</span></button>
          </li>)}</ul>
        </details>}
        {!!unclassifiedMatched && <div className={styles.unclassified}>
          <button type="button" aria-pressed={selected === ""} onClick={() => onSelect("")}>未标注技能的要求 <strong>{unclassifiedMatched}</strong></button>
          <button type="button" className={styles.cardEvidence} aria-haspopup="dialog" aria-controls="skill-evidence-drawer"
            aria-label="查看依据：未标注技能的要求" onClick={event => openEvidence("", event.currentTarget)}>查看依据 <span aria-hidden="true">→</span></button>
        </div>}
        {!landscape.contextCount && !state.busy && <p className={styles.noRecords}>已读取报告中暂无技能或要求记录。</p>}
        {!!landscape.contextCount && !visibleSkills.length && !unclassifiedMatched && <p className={styles.noRecords}>当前筛选没有匹配的要求记录。<button type="button" className="btn-secondary btn-compact" onClick={() => onFilterChange?.("all")}>查看全部记录</button></p>}
      </section>
      <dialog ref={dialog} id="skill-evidence-drawer" className={`job-workspace-drawer ${styles.evidenceDrawer}`}
        aria-labelledby="skill-evidence-title" onClose={restoreFocus}
        onClick={event => { if (event.target === event.currentTarget) dialog.current?.close(); }}>
        <div className="job-workspace-drawer-inner">
          <header className="job-workspace-drawer-heading">
            <h2 id="skill-evidence-title" className="section-title">{selected === "" ? "未标注技能的要求" : skill?.name} · 材料依据</h2>
            <button type="button" className="btn-secondary" onClick={() => dialog.current?.close()}>关闭</button>
          </header>
          <SkillContextRecords contexts={contexts} skillKey={selected ?? ""} />
        </div>
      </dialog>
    </div>}
  </div>;
}
