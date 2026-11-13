"use client";
import { openStudentMessages } from "./StudentMessages";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { displayIdentity, identityLabel } from "@/lib/demo-display-identity.js";

export type AccountMenuProps = { name: string; identityId?: string; unreadCount: number | null; busy: boolean; onLogout: () => void };
export default function AccountMenu({ name: originalName, identityId, unreadCount, busy, onLogout, role = "student" }: AccountMenuProps & { role?: "student" | "enterprise" }) {
  const identity = displayIdentity(originalName, identityId);
  const name = identity.name;
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
  const linkClass = "flex min-h-11 items-center rounded-lg px-3 py-2 text-slate-700 hover:bg-[#e7efe9] hover:text-[#1d4a40]";
  return <details ref={menu} className="account-menu relative ml-auto">
    <summary aria-label={`${roleLabel}账户：${identityLabel(originalName, identityId)}${unreadCount ? `，${unreadCount} 条未读通知` : ""}`} className={`flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-50 [&::-webkit-details-marker]:hidden ${enterprise ? "max-w-[min(12rem,48vw)] lg:max-w-[17rem]" : ""}`}>
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#e7efe9] text-[#1d4a40]" aria-hidden="true">{name.slice(0,1)}</span>
      <span className="min-w-0 max-w-24 truncate sm:max-w-32 lg:max-w-40" title={name}><span className="hidden sm:inline">{roleLabel} · </span>{name}</span>
      {!!unreadCount && <span className="shrink-0 whitespace-nowrap rounded-full bg-[#1d4a40] px-2 py-0.5 text-xs text-white">{unreadCount > 99 ? "99+" : unreadCount}<span className="hidden sm:inline">{enterprise ? "" : " 未读"}</span></span>}
      <span aria-hidden="true">▾</span>
    </summary>
    <nav aria-label={`${roleLabel}账户`} className="absolute right-0 top-full z-20 mt-2 w-60 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
      <p className="break-words border-b border-slate-100 px-3 py-2 text-xs text-slate-500">{name} · {roleLabel}</p>
      {identity.isExample && <details className="border-b border-slate-100 px-3 py-2 text-sm text-slate-600"><summary className="disclosure">数据说明</summary><p className="pb-2 leading-6">此账户用于功能体验，人物信息及相关材料为虚构资料。</p></details>}
      {!enterprise && <Link className={linkClass} href="/applications" onClick={close}>求职工作台</Link>}
      <Link className={linkClass} href={enterprise ? "/notifications" : "/applications?messages=1"} onClick={event => {
        close();
        if (!enterprise && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
          event.preventDefault();
          openStudentMessages(menu.current?.querySelector("summary"));
        }
      }}>{enterprise ? "通知" : "消息"}{unreadCount === null ? "" : `（${unreadCount} 未读）`}</Link>
      <div className="mt-1 border-t border-slate-100 pt-1"><button className={`${linkClass} w-full text-left`} disabled={busy} onClick={()=>{close();onLogout();}}>{busy ? "退出中…" : "退出登录"}</button></div>
    </nav>
  </details>;
}


