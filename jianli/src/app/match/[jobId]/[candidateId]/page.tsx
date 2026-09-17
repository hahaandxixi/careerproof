import Link from "next/link";

export default function LegacyMatchPage() {
  return <div className="panel text-center"><h1 className="text-xl font-semibold">匹配报告已迁移</h1><p className="my-4 text-sm text-slate-500">请选择真实岗位和自己的材料版本生成报告。旧演示地址不再计算或展示结果。</p><Link className="btn" href="/reports">我的匹配报告</Link></div>;
}
