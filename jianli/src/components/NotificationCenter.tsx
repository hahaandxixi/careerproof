"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import type { NotificationPage } from "@/lib/api/domain";
import { notificationHref, notificationsChanged } from "@/lib/notification-session";
import AccessGate from "./AccessGate";
import { useAuth } from "./AuthProvider";

export default function NotificationCenter() {
  const { user } = useAuth();
  return <AccessGate roles={["student", "enterprise"]}><Workspace key={user?.id} /></AccessGate>;
}
function Workspace() {
  const router = useRouter();
  const generation = useRef(0), locked = useRef(false);
  const [data, setData] = useState<NotificationPage | null>(null);
  const [page, setPage] = useState(1), [unread, setUnread] = useState(false);
  const [pageSize, setPageSize] = useState(20);
  const [revision, setRevision] = useState(0), [busy, setBusy] = useState(false), [error, setError] = useState("");
  useEffect(() => {
    const ticket = ++generation.current; setData(null); setError(""); setBusy(true);
    if (document.visibilityState !== "hidden") {
      void api.notifications(page, unread, pageSize).then(result => { if (ticket === generation.current) { if (result.page !== page) setPage(result.page); else setData(result); notificationsChanged(); } })
        .catch(reason => { if (ticket === generation.current) setError(errorMessage(reason)); })
        .finally(() => { if (ticket === generation.current) setBusy(false); });
    }
    const visibility = () => {
      if (document.visibilityState === "hidden") { ++generation.current; setData(null); setError(""); setBusy(false); }
      else setRevision(value => value + 1);
    };
    document.addEventListener("visibilitychange", visibility);
    return () => { ++generation.current; document.removeEventListener("visibilitychange", visibility); };
  }, [page, pageSize, unread, revision]);
  async function act(operation: () => Promise<unknown>, id?: string) {
    if (locked.current) return;
    locked.current = true; const ticket = ++generation.current; setBusy(true); setError("");
    try {
      if (id) {
        const target = await api.notificationTarget(id);
        if (ticket !== generation.current) return;
        if (!notificationHref(target.href)) throw new Error("通知目的地无效，请刷新。");
        await api.readNotification(id);
        if (ticket !== generation.current) return;
        notificationsChanged(); router.push(target.href);
      } else {
        await operation(); if (ticket !== generation.current) return;
        notificationsChanged(); setRevision(value => value + 1);
      }
    } catch (reason) { if (ticket === generation.current) setError(errorMessage(reason)); }
    finally { locked.current = false; if (ticket === generation.current) setBusy(false); }
  }
  return <div className="space-y-5"><h1 className="text-3xl font-bold">通知中心</h1>
    <p className="text-sm leading-6 text-slate-600">在这里查看投递进度与企业回应。查看或下载不代表面试或录用。</p>
    <details className="text-xs text-slate-500"><summary className="cursor-pointer py-2 text-indigo-700">通知说明</summary><p className="mt-2 leading-5">投递、查看、下载、回复和撤回会产生站内通知。阅读通知不等于阅读报告，历史事件不补发。打开投递时仍会核对授权；撤回后旧通知不能打开报告。</p></details>
    <div className="flex flex-wrap items-center gap-3"><button aria-pressed={!unread} className="selection-toggle" disabled={busy} onClick={() => { setPage(1); setUnread(false); }}>全部</button><button aria-pressed={unread} className="selection-toggle" disabled={busy} onClick={() => { setPage(1); setUnread(true); }}>未读</button><button className="text-indigo-700 underline" disabled={busy} onClick={() => setRevision(value => value + 1)}>刷新通知</button><button className="text-indigo-700 underline" disabled={busy || !data?.unreadCount} onClick={() => void act(api.readAllNotifications)}>全部标为已读</button></div>
    {busy && <p role="status">正在读取或更新通知…</p>}{error && <p role="alert" className="panel text-rose-700">{error}</p>}
    <label className="flex items-center gap-2 text-sm">每页通知数<select className="field w-auto" disabled={busy} value={pageSize} onChange={event => { setPage(1); setPageSize(Number(event.target.value)); }}><option value={20}>20条</option><option value={50}>50条</option></select></label>
    {data && <><p className="text-sm">未读 {data.unreadCount} 条 · 当前筛选共 {data.total} 条</p>
      {!data.items.length && <p className="panel">{unread ? "暂无未读通知。" : "暂无通知，新的投递事件会显示在这里。"}</p>}
      <ul className="space-y-3">{data.items.map(item => <li key={item.id} className="panel space-y-3"><h2 className="font-semibold">{item.title}</h2><p className="text-xs text-slate-500">{new Date(item.createdAt).toLocaleString()} · {item.readAt ? "已读" : "未读"}</p><div className="flex flex-wrap gap-4">{item.accessible ? <button className="text-sm text-indigo-700 underline" disabled={busy} onClick={() => void act(() => Promise.resolve(), item.id)}>核对授权并打开投递</button> : <p className="text-sm text-slate-500">当前投递不可访问，不能从旧通知查看报告或材料。</p>}{!item.readAt && <button className="text-sm underline" disabled={busy} onClick={() => void act(() => api.readNotification(item.id))}>标为已读</button>}</div></li>)}</ul>
      <div className="flex gap-4"><button className="btn-secondary" disabled={busy || page === 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {page} 页</span><button className="btn-secondary" disabled={busy || page * data.pageSize >= data.total} onClick={() => setPage(value => value + 1)}>下一页</button></div></>}
  </div>;
}
