"use client";

import Link from "next/link";
import { useAuth } from "./AuthProvider";
import type { UserRole } from "@/lib/api/client";

export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return <div role="alert" className="rounded-xl bg-rose-50 p-4 text-sm text-rose-800">
    <p>{message}</p>{retry && <button className="mt-2 font-medium underline" onClick={retry}>重新加载</button>}
  </div>;
}

export default function AccessGate({ children, roles }: { children: React.ReactNode; roles?: UserRole[] }) {
  const { user, status, error, reload } = useAuth();
  if (status === "loading") return <p className="py-12 text-center text-slate-500">正在确认登录状态…</p>;
  if (status === "error") return <ErrorNotice message={`暂时无法确认会话：${error}`} retry={() => void reload()} />;
  if (!user) return <div className="panel text-center"><h1 className="text-xl font-semibold">请先登录</h1><p className="my-3 text-sm text-slate-500">登录后查看属于你的材料、任务和报告。</p><Link className="btn" href="/login">前往登录</Link></div>;
  if (roles && !roles.includes(user.role)) return <div className="panel text-center">当前账号没有使用此功能的权限。<Link href="/jobs" className="ml-2 text-indigo-600">返回岗位列表</Link></div>;
  return <div key={user.id}>{children}</div>;
}
