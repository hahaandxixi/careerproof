"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

export default function StudentAccountMenu({ name, unreadCount, busy, onLogout }: { name: string; unreadCount: number | null; busy: boolean; onLogout: () => void }) {
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
    <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-indigo-700" aria-hidden="true">{name.slice(0,1)}</span>
      <span className="max-w-24 truncate sm:max-w-32" title={name}><span className="hidden sm:inline">学生账户 · </span>{name}</span>
      {!!unreadCount && <span className="rounded-full bg-indigo-600 px-2 py-0.5 text-xs text-white">{unreadCount} 未读</span>}
      <span aria-hidden="true">▾</span>
    </summary>
    <nav aria-label="学生账户" className="absolute right-0 top-full z-20 mt-2 w-60 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
      <p className="break-words border-b border-slate-100 px-3 py-2 text-xs text-slate-500">{name} · 学生</p>
      <Link className={linkClass} href="/" onClick={close}>工作台</Link>
      <Link className={linkClass} href="/notifications" onClick={close}>通知{unreadCount === null ? "" : `（${unreadCount} 未读）`}</Link>
      <div className="mt-1 border-t border-slate-100 pt-1"><button className={`${linkClass} w-full text-left`} disabled={busy} onClick={()=>{close();onLogout();}}>{busy ? "退出中…" : "退出登录"}</button></div>
    </nav>
  </details>;
}
