import Link from "next/link";

export default function CandidatePage() {
  return <div className="panel text-center"><h1 className="text-xl font-semibold">候选人资料通过授权报告访问</h1><p className="my-4 text-sm text-slate-500">旧演示候选人已停用。当前仅在有访问权限的匹配报告中展示相关材料证据。</p><Link className="btn" href="/reports">查看匹配报告</Link></div>;
}
