import type { ApplicationView } from "@/lib/api/client";

export default function SkillRadar({dimensions}:{dimensions:ApplicationView["dimensions"]}){
  if(dimensions.length<3)return <p className="text-xs text-slate-500">少于3项要求，使用逐项表格对照，不绘制雷达图。</p>;
  const point=(index:number,ratio:number)=>{
    const angle=index*2*Math.PI/dimensions.length-Math.PI/2;
    return {x:160+100*ratio*Math.cos(angle),y:160+100*ratio*Math.sin(angle)};
  };
  return <section className="rounded-lg border border-slate-200 p-3">
    <h3 className="font-semibold">岗位要求雷达 · 原报告分数</h3>
    <p className="mt-2 text-xs leading-6 text-slate-500">实心点表示有项目证据的分数，空心点表示仅自述或缺材料；不可评项标为“—”。不填充面积，避免把缺失证据误当作能力为零。</p>
    <svg className="mx-auto w-full max-w-sm" viewBox="0 0 320 320" role="img" aria-label="各岗位要求原报告分数雷达，对照下方编号表查看缺证据与不可评项">
      {[0.25,0.5,0.75,1].map(r=><circle key={r} cx="160" cy="160" r={100*r} fill="none" stroke="#e2e8f0"/>)}
      {dimensions.map((d,i)=>{const end=point(i,1),label=point(i,1.18);const assessed=d.score!==null&&d.verdict!=="unsupported";const dot=point(i,Math.max(0,Math.min(100,d.score??0))/100);const backed=["supported","verified","partial"].includes(d.verdict);return <g key={d.requirementId}>
        <line x1="160" y1="160" x2={end.x} y2={end.y} stroke="#cbd5e1"/>
        <text x={label.x} y={label.y} textAnchor="middle" dominantBaseline="middle" fontSize="12" fill="#334155">{i+1}{!assessed?" —":""}</text>
        {assessed&&<circle cx={dot.x} cy={dot.y} r="5" fill={backed?"#4f46e5":"white"} stroke={backed?"#4f46e5":"#d97706"} strokeWidth="2"><title>{d.title}：{d.score}；{d.verdict}</title></circle>}
      </g>;})}
    </svg>
    <ol className="grid gap-2 text-xs text-slate-600 sm:grid-cols-2">{dimensions.map((d,i)=><li key={d.requirementId}>{i+1}. {d.skill||d.title}：{d.score??"不可评"}{["gap","claimed_only"].includes(d.verdict)?"（缺材料或仅自述）":""}</li>)}</ol>
  </section>;
}
