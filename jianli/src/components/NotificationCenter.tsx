"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import type { NotificationItem, NotificationPage } from "@/lib/api/domain";
import { notificationHref, notificationsChanged } from "@/lib/notification-session";
import AccessGate from "./AccessGate";
import { useAuth } from "./AuthProvider";
import ListPagination from "./ListPagination";

export function NotificationCard({ item, busy, onOpen, onRead }: {
  item: NotificationItem; busy: boolean; onOpen(id: string): void; onRead(id: string): void;
}) {
  return <li className="workspace-row space-y-2">
    <div className="flex flex-wrap items-baseline justify-between gap-3"><h2 className="flex min-w-0 items-baseline gap-2 font-semibold">{!item.readAt && <span aria-hidden="true" className="h-2 w-2 shrink-0 translate-y-[-1px] rounded-full bg-indigo-600" />}<span className="break-words">{item.title}</span></h2><p className="shrink-0 text-sm text-slate-600"><time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString()}</time> · {item.readAt ? "已读" : "未读"}</p></div>
    <div className="card-actions">{item.accessible ? <button type="button" className="btn-secondary" disabled={busy} onClick={() => onOpen(item.id)}>查看投递</button> : <p className="text-sm text-slate-600">当前投递不可访问，不能从旧通知查看报告或材料。</p>}{!item.readAt && <button type="button" className="btn-quiet" disabled={busy} onClick={() => onRead(item.id)}>标为已读</button>}</div>
  </li>;
}

export default function NotificationCenter() {
  const { user } = useAuth();
  return <AccessGate roles={["student", "enterprise"]}><Workspace key={user?.id} /></AccessGate>;
}
function Workspace() {
  const { user } = useAuth();
  const router = useRouter();
  // generation 只在 effect 体、act 与可见性处理里推进（清理不读取）；
  // alive 在清理中只做常量赋值：卸载后在途回执一律丢弃，依赖变化由
  // effect 重跑时的新票据使旧回执失效，行为与原先清理内推进计数器一致。
  const generation = useRef(0), locked = useRef(false), alive = useRef(true);
  const [data, setData] = useState<NotificationPage | null>(null);
  const [page, setPage] = useState(1), [unread, setUnread] = useState(false);
  const [pageSize, setPageSize] = useState(20);
  const [revision, setRevision] = useState(0), [busy, setBusy] = useState(false), [error, setError] = useState("");
  useEffect(() => {
    alive.current = true;
    const ticket = ++generation.current; setData(null); setError(""); setBusy(true);
    if (document.visibilityState !== "hidden") {
      void api.notifications(page, unread, pageSize).then(result => { if (alive.current && ticket === generation.current) { if (result.page !== page) setPage(result.page); else setData(result); notificationsChanged(); } })
        .catch(reason => { if (alive.current && ticket === generation.current) setError(errorMessage(reason)); })
        .finally(() => { if (alive.current && ticket === generation.current) setBusy(false); });
    }
    const visibility = () => {
      if (document.visibilityState === "hidden") { ++generation.current; setData(null); setError(""); setBusy(false); }
      else setRevision(value => value + 1);
    };
    document.addEventListener("visibilitychange", visibility);
    return () => { alive.current = false; document.removeEventListener("visibilitychange", visibility); };
  }, [page, pageSize, unread, revision]);
  async function act(operation: () => Promise<unknown>, id?: string) {
    if (locked.current) return;
    locked.current = true; const ticket = ++generation.current; setBusy(true); setError("");
    try {
      if (id) {
        const target = await api.notificationTarget(id);
        if (!alive.current || ticket !== generation.current) return;
        if (!notificationHref(target.href)) throw new Error("通知目的地无效，请刷新。");
        await api.readNotification(id);
        if (!alive.current || ticket !== generation.current) return;
        notificationsChanged(); router.push(target.href);
      } else {
        await operation(); if (!alive.current || ticket !== generation.current) return;
        notificationsChanged(); setRevision(value => value + 1);
      }
    } catch (reason) { if (alive.current && ticket === generation.current) setError(errorMessage(reason)); }
    finally { locked.current = false; if (alive.current && ticket === generation.current) setBusy(false); }
  }
  return <div className="space-y-5"><h1 className="page-title">通知中心</h1>
    <div className="flex flex-wrap items-center gap-3"><button aria-pressed={!unread} className="selection-toggle" disabled={busy} onClick={() => { setPage(1); setUnread(false); }}>全部</button><button aria-pressed={unread} className="selection-toggle" disabled={busy} onClick={() => { setPage(1); setUnread(true); }}>未读</button><button className="btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>刷新</button><button className="btn-quiet" disabled={busy || !data?.unreadCount} onClick={() => void act(api.readAllNotifications)}>全部标为已读</button></div>
    {busy && <p role="status">正在读取或更新通知…</p>}{error && <p role="alert" className="panel text-rose-700">{error}</p>}
    <label className="flex items-center gap-2 text-sm">每页通知数<select className="field w-auto" disabled={busy} value={pageSize} onChange={event => { setPage(1); setPageSize(Number(event.target.value)); }}><option value={20}>20条</option><option value={50}>50条</option></select></label>
    {data && <><p className="text-sm">未读 {data.unreadCount} 条 · 当前筛选共 {data.total} 条</p>
      {!data.items.length && <div className="panel"><p className="reading-copy">{unread ? "暂无未读通知，可切换到全部查看历史记录。" : "暂无通知，新的投递事件会显示在这里。"}</p>{!unread && <Link className="btn-secondary mt-3" href={user?.role === "enterprise" ? "/jobs/mine" : "/reports"}>{user?.role === "enterprise" ? "查看我的岗位" : "查看我的报告"}</Link>}</div>}
      <ul className={data.items.length ? "workspace-sheet workspace-list" : undefined}>{data.items.map(item => <NotificationCard key={item.id} item={item} busy={busy} onOpen={id => void act(() => Promise.resolve(), id)} onRead={id => void act(() => api.readNotification(id))}/>)}</ul>
      <ListPagination label="通知分页" value={data} busy={busy} onPage={setPage}/></>}
  </div>;
}
