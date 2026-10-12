"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "./AuthProvider";
import NotificationLink from "./NotificationLink";
import StudentAccountMenu from "./StudentAccountMenu";
import { errorMessage } from "@/lib/api/client";

export default function SiteHeader() {
  const { user, status, logout, reload } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function handleLogout() {
    setBusy(true); setError("");
    try { await logout(); router.push("/"); router.refresh(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
    <div className="mx-auto flex min-h-16 max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
      <Link href="/" className="font-semibold text-indigo-700">职证 CareerProof</Link>
      <nav aria-label="主导航" className="flex flex-wrap items-center gap-4 text-sm">
        <Link href="/jobs">岗位发现</Link>
        {user?.role === "student" && <Link href="/recommendations">职业推荐</Link>}
        {(user?.role === "student" || user?.role === "admin") && <Link href="/reports">我的匹配报告</Link>}
        {(user?.role === "enterprise" || user?.role === "admin") && <>
          <Link href="/jobs/mine">岗位管理</Link><Link href="/jobs/new" className="text-indigo-600">发布岗位</Link>
        </>}
        {user?.role !== "student" && <NotificationLink />}
        {status === "loading" ? <span className="text-slate-400">确认会话中…</span> :
          status === "error" ? <button onClick={() => void reload()} className="text-amber-700">服务连接异常 · 重试</button> :
          user?.role === "student" ? <NotificationLink render={count => <StudentAccountMenu name={user.displayName} unreadCount={count} busy={busy} onLogout={() => void handleLogout()} />} /> :
          user ? <><span className="max-w-28 truncate text-slate-500">{user.displayName}</span><button disabled={busy} onClick={handleLogout}>{busy ? "退出中…" : "退出"}</button></> :
          <><Link href="/login">登录</Link><Link href="/register" className="text-indigo-600">注册</Link></>}
      </nav>
    </div>
    {error && <p role="alert" className="mx-auto max-w-6xl px-4 pb-3 text-sm text-rose-700">{error}</p>}
  </header>;
}
