"use client";
import { displayJobCompany, displayJobTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import ListPagination from "./ListPagination";
import { api, ApiError, errorMessage } from "@/lib/api/client";
import type { ApplicationView } from "@/lib/api/client";
import { applicationAnchorId } from "@/lib/notification-session";
import { createApplicationListSession, type ApplicationListState } from "@/lib/application-list-session";
import { createRefreshGate } from "@/lib/refresh-gate";
import { applicationNextAction, applicationStatusText } from "@/lib/application-display";
import AccessGate from "./AccessGate";
import ApplicationReply from "./ApplicationReply";
import { useAuth } from "./AuthProvider";
import JobWorkspaceNextStep from "./JobWorkspaceNextStep";

// 传智杯44：单条投递卡片是无状态展示组件，突出岗位/公司/状态/企业回复/下一动作；
// 状态和近期进度基于原事件；撤回、重新投递和报告链接使用既有入口。
export function ApplicationItemCard({item, confirming, busy, onRequestWithdraw, onConfirmWithdraw, onCancelWithdraw}: {
  item: ApplicationView;
  confirming: boolean;
  busy: boolean;
  onRequestWithdraw(id: string): void;
  onConfirmWithdraw(id: string): void;
  onCancelWithdraw(): void;
}) {
  const reportHref = `/reports/${encodeURIComponent(item.reportId)}`;
  const eventLabel = (type: string) => ({ submitted: "授权投递", viewed: "企业查看", downloaded: "企业下载", replied: "企业回复", withdrawn: "撤回授权" } as Record<string, string>)[type] ?? "投递记录";
  const eventNodes = item.events.filter(event => event.detail?.trim()).slice(-3);
  return <article id={`application-${item.id}`} className="workspace-row application-record" tabIndex={-1}>
    <div className="application-record-head">
      <div className="min-w-0"><h2 className="text-xl font-semibold">{displayJobTitle(item.jobTitle, item.jobId)}</h2><p className="mt-1 break-words text-sm text-slate-600">{displayJobCompany(item.companyName, item.jobId)}</p></div>
      <span className="status-chip application-status">{applicationStatusText(item.status)}</span>
    </div>
    {!item.replyText&&item.status!=="withdrawn"&&<p className="text-sm leading-6 text-slate-600">{applicationNextAction(item.status)}</p>}
    <ApplicationReply application={item}/>
    {!!item.replyReferences?.length&&<div className="rounded-lg bg-slate-50 p-3 text-sm"><p className="font-medium">企业回复对应的原报告位置</p><ul className="mt-2 space-y-2">{item.replyReferences.map(reference=><li key={reference.requirementId} className="break-words"><Link className="text-brand-ink underline" href={`${reportHref}#requirement-${encodeURIComponent(reference.requirementId)}`}>{`第${item.dimensions.findIndex(d=>d.requirementId===reference.requirementId)+1}项：`}{item.dimensions.find(d=>d.requirementId===reference.requirementId)?.title || "查看岗位要求"}</Link><Link className="ml-2 text-xs text-brand-ink underline" href={`${reportHref}?enterpriseReply=${encodeURIComponent(reference.requirementId)}#requirement-${encodeURIComponent(reference.requirementId)}`}>带着这项问题补证 →</Link>{reference.citationIds.length>0&&<span className="ml-2 text-xs">引用：{reference.citationIds.map((id,index)=><span key={id}>{index>0?"、":""}<Link className="text-brand-ink underline" href={`${reportHref}#citation-${encodeURIComponent(id)}`}>{id}</Link></span>)}</span>}</li>)}</ul></div>}
    {item.status==="withdrawn"&&<p className="text-sm text-slate-600">本次授权已撤回。<Link className="ml-2 text-brand-ink underline" href={`${reportHref}#application-submit`}>重新确认授权并投递</Link>；也可从新版报告投递，原记录与企业回复不会被覆盖。</p>}
    <div className="card-actions application-actions"><Link className="btn-secondary" href={reportHref}>查看关联报告</Link>{item.status!=="withdrawn"&&!confirming&&<button type="button" disabled={busy} className="btn-danger-quiet" onClick={()=>onRequestWithdraw(item.id)}>撤回授权</button>}</div>
    {item.status!=="withdrawn"&&confirming&&<div className="space-y-2 rounded-lg bg-rose-50 p-3"><p className="text-sm text-rose-900">撤回后企业不能继续访问本份报告或下载。已下载副本无法追回，如需再次分享，可从报告页重新确认授权；将创建新的投递，旧记录继续保留。</p><div className="flex flex-wrap gap-2"><button type="button" className="btn-danger-quiet border border-rose-300" disabled={busy} onClick={()=>onConfirmWithdraw(item.id)}>确认撤回授权</button><button type="button" className="btn-secondary" disabled={busy} onClick={onCancelWithdraw}>取消</button></div></div>}
    {!!eventNodes.length && <ol className="application-event-flow" aria-label="已保存的投递事件">{eventNodes.map((e,index)=><li key={`${e.type}:${e.at}:${index}`}><span className="application-event-dot" aria-hidden="true"/><div><strong>{eventLabel(e.type)}</strong><time dateTime={e.at}>{new Date(e.at).toLocaleString("zh-CN")}</time></div></li>)}</ol>}
  </article>;
}

export default function ApplicationList() {
  const { user } = useAuth();
  return <AccessGate roles={["student"]}><Workspace key={user?.id} /></AccessGate>;
}

const applicationViews = [
  ["all", "全部投递"], ["waiting", "等待企业回复"], ["action", "待我核对"], ["withdrawn", "已撤回"],
] as const;
type Detail = { id: string; item?: ApplicationView; error?: string; unavailable?: boolean; focus?: boolean };

function Workspace() {
  const search = useSearchParams();
  const savedQuery = (search.get("q") ?? "").slice(0, 200);
  const savedView = search.get("view");
  const view = applicationViews.find(([value]) => value === savedView)?.[0] ?? "all";
  const parsedPage = Number(search.get("page"));
  const page = Number.isSafeInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1;
  const criteria = useRef({ page, q: savedQuery, view });
  const [query, setQuery] = useState(savedQuery);
  const [state, setState] = useState<ApplicationListState>({ items: [], loading: true, error: "" });
  const [detail, setDetail] = useState<Detail | null>(null);
  const [revokeId, setRevokeId] = useState<string | null>(null);
  const [overviewRevision, setOverviewRevision] = useState(0);
  const selected = useRef<string | null>(null);
  const detailTicket = useRef(0);

  const session = useMemo(() => createApplicationListSession({
    list: () => api.myApplications(criteria.current.page, 20, undefined, { q: criteria.current.q, view: criteria.current.view }),
    withdraw: api.withdrawApplication, errorMessage,
  }, setState), []);

  const invalidateDetail = useCallback(() => { ++detailTicket.current; }, []);

  const loadDetail = useCallback(async (id: string, focus = false) => {
    const ticket = ++detailTicket.current;
    selected.current = id;
    setDetail({ id });
    try {
      const item = await api.applicationDetail(id);
      if (ticket !== detailTicket.current) return;
      setDetail({ id, item, focus });
    } catch (error) {
      if (ticket !== detailTicket.current) return;
      const unavailable = error instanceof ApiError && [403, 404].includes(error.status);
      setDetail({ id, error: unavailable ? "这条投递当前不可访问。" : errorMessage(error), unavailable });
    }
  }, []);

  function storeSelection(id: string) {
    const url = new URL(location.href);
    url.hash = `application-${id}`;
    history.replaceState(null, "", url);
  }

  const openMessageTarget = useCallback((item: ApplicationView) => {
    ++detailTicket.current;
    selected.current = item.id;
    storeSelection(item.id);
    setRevokeId(null);
    setDetail({ id: item.id, item, focus: true });
  }, []);
  useEffect(() => {
    const open = (event: Event) => openMessageTarget((event as CustomEvent<ApplicationView>).detail);
    window.addEventListener("careerproof:message-application", open);
    return () => window.removeEventListener("careerproof:message-application", open);
  }, [openMessageTarget]);
  useEffect(() => {
    if (detail?.focus && detail.item) {
      const card = document.getElementById(`application-${detail.id}`);
      card?.focus({ preventScroll: true });
      card?.scrollIntoView({ block: "nearest" });
    }
  }, [detail]);

  useEffect(() => {
    session.activate();
    const openAnchor = () => {
      const id = applicationAnchorId();
      if (!id || document.visibilityState === "hidden") return;
      setRevokeId(null);
      void loadDetail(id, true);
    };
    const onHashChange = () => {
      if (!applicationAnchorId()) return;
          openAnchor();
    };
    const refresh = () => {
      if (document.visibilityState === "hidden") return;
      setRevokeId(null);
      void session.refresh();
      setOverviewRevision(value => value + 1);
      if (selected.current) void loadDetail(selected.current);
    };
    const gate = createRefreshGate(refresh);
    const visibility = () => {
      setRevokeId(null);
      if (document.visibilityState === "hidden") {
        invalidateDetail();
        setDetail(null);
        session.clear();
        gate.reset();
      } else gate.trigger();
    };
    const focusWindow = () => gate.trigger();
    const blurWindow = () => gate.reset();
    openAnchor();
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("focus", focusWindow);
    window.addEventListener("blur", blurWindow);
    window.addEventListener("hashchange", onHashChange);
    return () => {
      invalidateDetail();
      session.dispose();
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("focus", focusWindow);
      window.removeEventListener("blur", blurWindow);
      window.removeEventListener("hashchange", onHashChange);
    };
  }, [invalidateDetail, loadDetail, session]);

  useEffect(() => {
    criteria.current = { page, q: savedQuery, view };
    setQuery(savedQuery);
    setRevokeId(null);
    if (document.visibilityState !== "hidden") void session.refresh();
  }, [page, savedQuery, view, session]);

  useEffect(() => {
    if (selected.current || !state.items.length || document.visibilityState === "hidden") return;
    const item = state.items[0];
    selected.current = item.id;
    setDetail({ id: item.id, item });
  }, [state.items]);

  function filter(q: string, nextView: string, nextPage = 1) {
    const url = new URL(location.href);
    for (const [key, value] of [["q", q.trim()], ["view", nextView === "all" ? "" : nextView], ["page", nextPage === 1 ? "" : String(nextPage)]]) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    if (url.href !== location.href) history.pushState(null, "", url);
    else void session.refresh();
  }

  const { items, error, loading: busy } = state;
  const filtered = savedQuery || view !== "all";
  const detailOutsidePage = detail?.item && !items.some(item => item.id === detail.id);
  const refresh = () => {
    setRevokeId(null);
    void session.refresh();
    setOverviewRevision(value => value + 1);
    if (selected.current) void loadDetail(selected.current);
  };

  return <div className="application-workspace student-job-workspace">
    <JobWorkspaceNextStep refreshVersion={overviewRevision} onViewReplies={() => filter("", "action")} onOpenReply={id => {
      storeSelection(id);
      setRevokeId(null);
      void loadDetail(id, true);
    }} />
    <section className="job-workspace-applications" aria-labelledby="workspace-applications-title">
      <h2 id="workspace-applications-title" className="section-title">投递记录</h2>
      <form className="application-toolbar" onSubmit={event => { event.preventDefault(); filter(query, view); }}>
        <div className="application-search-actions">
          <label className="min-w-0"><span className="sr-only">查找岗位或企业</span><input className="field" placeholder="查找岗位或企业" type="search" value={query} maxLength={200} onChange={event => setQuery(event.target.value)} /></label>
          <button className="btn btn-compact whitespace-nowrap" disabled={busy}>搜索</button>
          <button className="btn-quiet btn-compact whitespace-nowrap" type="button" disabled={busy} onClick={() => { setQuery(""); filter("", "all"); }}>重置</button>
          <button type="button" className="btn-secondary btn-compact whitespace-nowrap" disabled={busy} onClick={refresh}>刷新</button>
        </div>
        <div role="group" aria-label="投递状态" className="application-view-actions">
          {applicationViews.map(([value, label]) => <button key={value} type="button" className="selection-toggle" aria-pressed={view === value} disabled={busy} onClick={() => filter(query, value)}>{label}</button>)}
        </div>
      </form>
      <div className="application-master-detail">
        <div className="application-record-list">
          {error && <p role="alert" className="job-workspace-list-message text-rose-700">{error}</p>}
          {busy && <p role="status" className="job-workspace-list-message">正在读取投递…</p>}
          {!items.length && !busy && !error && <p className="job-workspace-list-message">{filtered ? "没有符合条件的投递。" : "暂无投递记录。"}</p>}
          {!!items.length && <nav aria-label="投递记录">
            {items.map(item => {
              const isSelected = detail?.id === item.id;
              return <button key={item.id} type="button" className={`application-record-summary ${isSelected ? "is-selected" : ""}`} aria-pressed={isSelected}
                onClick={() => {
                  storeSelection(item.id);
                  setRevokeId(null);
                  void loadDetail(item.id);
                }}>
                <strong>{displayJobTitle(item.jobTitle, item.jobId)}</strong>
                <span>{displayJobCompany(item.companyName, item.jobId)}</span>
                <span className="application-summary-status">{applicationStatusText(item.status)}</span>
                <span>{new Date(item.events.at(-1)?.at ?? item.createdAt).toLocaleDateString("zh-CN")}</span>
              </button>;
            })}
          </nav>}
          {state.pagination && <div className="job-workspace-pagination">
            <ListPagination label="投递分页" value={state.pagination} busy={busy} onPage={value => filter(savedQuery, view, value)} />
          </div>}
        </div>
        <div className="application-record-detail">
          {!detail && <p className="reading-copy">{!busy && !filtered && !error && !items.length ? "核对报告后，你可以决定是否向企业投递。" : "选择一条投递查看详情。"}</p>}
          {detail && !detail.item && !detail.error && <p role="status">正在读取投递详情…</p>}
          {detail?.error && <div role="alert" className="space-y-2">
            <p className="text-rose-700">{detail.error}</p>
            {!detail.unavailable && <button type="button" className="btn-secondary" onClick={() => void loadDetail(detail.id)}>重试读取</button>}
          </div>}
          {detailOutsidePage && !busy && <p className="job-workspace-outside">当前详情不在本页的投递列表中。</p>}
          {detail?.item && <ApplicationItemCard key={detail.id} item={detail.item} confirming={revokeId === detail.id} busy={busy}
            onRequestWithdraw={setRevokeId} onCancelWithdraw={() => setRevokeId(null)}
            onConfirmWithdraw={async id => {
              setRevokeId(null);
              await session.withdraw(id);
              setOverviewRevision(value => value + 1);
              if (selected.current === id && document.visibilityState !== "hidden") await loadDetail(id);
            }} />}
        </div>
      </div>
    </section>
  </div>;
}
