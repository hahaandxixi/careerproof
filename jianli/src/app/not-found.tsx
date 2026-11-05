import Link from "next/link";

export default function NotFound() {
  return <div className="panel space-y-3 text-center">
    <h1 className="page-title">没有找到这个页面</h1>
    <p className="text-sm leading-6 text-slate-600">地址可能已变更，或该内容需要登录后从对应入口访问。岗位、报告和投递记录请从导航进入。</p>
    <div className="flex flex-wrap justify-center gap-3 pt-2">
      <Link className="btn" href="/">回到首页</Link>
      <Link className="btn-secondary" href="/jobs">查看岗位</Link>
    </div>
  </div>;
}
