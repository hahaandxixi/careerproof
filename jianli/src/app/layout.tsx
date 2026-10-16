import type { Metadata } from "next";
import { AuthProvider } from "@/components/AuthProvider";
import SiteHeader from "@/components/SiteHeader";
import StudentFlowGuide from "@/components/StudentFlowGuide";
import "./globals.css";

export const metadata: Metadata = {
  title: "可追溯人才匹配平台",
  description:
    "关联真实简历、项目版本与岗位要求，提供可追溯的材料证据和匹配报告",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-white focus:p-3 focus:text-indigo-700">跳到主要内容</a>
        <AuthProvider>
          <SiteHeader />
          <main id="main-content" tabIndex={-1} className="mx-auto max-w-6xl px-4 py-8"><StudentFlowGuide />{children}</main>
          <footer className="mx-auto max-w-6xl px-4 py-8 text-center text-xs text-slate-400">
            规则检索 + AI 证据解释 · 模型不可用时自动降级 · 不执行上传的代码
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
