import Link from "next/link";
import HeatmapDemo from "@/components/HeatmapDemo";
export default function HeatmapDemoPage() { return <div className="mx-auto max-w-6xl space-y-5"><Link href="/demo" className="text-sm text-indigo-700">← 合成演示材料</Link><header><h1 className="text-2xl font-bold">企业热力图交互示例</h1><p className="mt-2 text-sm text-slate-600">无需生成报告即可体验筛选、候选人切换与岗位要求雷达。</p></header><HeatmapDemo/></div>; }
