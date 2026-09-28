"use client";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api/client";

export default function ArchivedMaterials({onRestore}:{onRestore:()=>void}){
  const [items,setItems]=useState<{id:string;name:string;kind:"resume"|"project"}[]>([]),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  async function load(){setBusy(true);setError("");try{const [r,p]=await Promise.all([api.listResumes(true),api.listProjects(true)]);setItems([...r.filter(v=>v.isArchived).map(v=>({id:v.id,name:v.title,kind:"resume" as const})),...p.filter(v=>v.isArchived).map(v=>({id:v.id,name:v.name,kind:"project" as const}))]);}catch(e){setError(errorMessage(e));}finally{setBusy(false);}}
  return <details className="panel" onToggle={e=>{if(e.currentTarget.open)void load();}}><summary className="cursor-pointer font-semibold">归档材料 · 旧测试记录与恢复</summary><p className="mt-3 text-sm text-slate-500">归档材料不出现在普通选择列表；原文件和已生成报告仍保留。恢复后可重新选择。</p>{error&&<p role="alert" className="text-rose-700">{error}</p>}<ul className="mt-3 max-h-72 space-y-2 overflow-y-auto">{items.map(item=><li key={item.kind+item.id} className="flex items-start justify-between gap-3 rounded-lg bg-slate-50 p-3 text-sm"><span className="min-w-0 break-words">{item.name}</span><button type="button" className="shrink-0 text-indigo-700 underline" disabled={busy} onClick={async()=>{setBusy(true);try{await api.archiveMaterial(item.kind,item.id,false);await load();onRestore();}catch(e){setError(errorMessage(e));}finally{setBusy(false);}}}>恢复</button></li>)}</ul>{!items.length&&!busy&&!error&&<p className="mt-3 text-sm">暂无归档材料。</p>}</details>;
}
