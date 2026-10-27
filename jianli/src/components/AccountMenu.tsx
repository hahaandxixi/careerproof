"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

export type AccountMenuProps = { name: string; unreadCount: number | null; busy: boolean; onLogout: () => void };
export default function AccountMenu({ name, unreadCount, busy, onLogout, role = "student" }: AccountMenuProps & { role?: "student" | "enterprise" }) {
  const enterprise = role === "enterprise";
  const roleLabel = enterprise ? "企业" : "学生";
  const menu = useRef<HTMLDetailsElement>(null);
  const pathname = usePathname();
  useEffect(() => { if (menu.current) menu.current.open = false; }, [pathname]);
  useEffect(() => {
    const closeOutside = (event: Event) => { if (menu.current && event.target instanceof Node && !menu.current.contains(event.target)) menu.current.open = false; };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && menu.current?.open) {
        menu.current.open = false;
        menu.current.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("focusin", closeOutside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", closeOutside); document.removeEventListener("focusin", closeOutside); document.removeEventListener("keydown", escape); };
  }, []);
  const close = () => { if (menu.current) menu.current.open = false; };
  const linkClass = "flex min-h-11 items-center rounded-lg px-3 py-2 text-slate-700 hover:bg-indigo-50 hover:text-indigo-700";
  return <details ref={menu} className="relative ml-auto">
    <summary aria-label={`${roleLabel}账户：${name}${unreadCount ? `，${unreadCount} 条未读通知` : ""}`} className={`flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-50 [&::-webkit-details-marker]:hidden ${enterprise ? "max-w-[min(12rem,48vw)]" : ""}`}>
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-indigo-700" aria-hidden="true">{name.slice(0,1)}</span>
      <span className="min-w-0 max-w-24 truncate sm:max-w-32" title={name}><span className="hidden sm:inline">{roleLabel}账户 · </span>{name}</span>
      {!!unreadCount && <span className="shrink-0 whitespace-nowrap rounded-full bg-indigo-600 px-2 py-0.5 text-xs text-white">{enterprise && unreadCount > 99 ? "99+" : unreadCount}{enterprise ? "" : " 未读"}</span>}
      <span aria-hidden="true">▾</span>
    </summary>
    <nav aria-label={`${roleLabel}账户`} className="absolute right-0 top-full z-20 mt-2 w-60 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
      <p className="break-words border-b border-slate-100 px-3 py-2 text-xs text-slate-500">{name} · {roleLabel}</p>
      {!enterprise && <Link className={linkClass} href="/" onClick={close}>工作台</Link>}
      {!enterprise && <Link className={linkClass} href="/growth" onClick={close}>历史补证记录</Link>}
      <Link className={linkClass} href="/notifications" onClick={close}>通知{unreadCount === null ? "" : `（${unreadCount} 未读）`}</Link>
      <div className="mt-1 border-t border-slate-100 pt-1"><button className={`${linkClass} w-full text-left`} disabled={busy} onClick={()=>{close();onLogout();}}>{busy ? "退出中…" : "退出登录"}</button></div>
    </nav>
  </details>;
}
