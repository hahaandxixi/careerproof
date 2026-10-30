"use client";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api/client";

export default function ArchivedMaterials({onRestore}:{onRestore:()=>void}){
  const [items,setItems]=useState<{id:string;name:string;kind:"resume"|"project"}[]>([]),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  async function load(){setBusy(true);setError("");try{const [r,p]=await Promise.all([api.listResumes(true),api.listProjects(true)]);setItems([...r.filter(v=>v.isArchived).map(v=>({id:v.id,name:v.title,kind:"resume" as const})),...p.filter(v=>v.isArchived).map(v=>({id:v.id,name:v.name,kind:"project" as const}))]);}catch(e){setError(errorMessage(e));}finally{setBusy(false);}}
  return <details className="text-sm" onToggle={e=>{if(e.currentTarget.open)void load();}}><summary className="disclosure">归档材料{items.length>0?`（${items.length}）`:""}</summary>{busy&&<p role="status" className="py-2 text-slate-600">正在读取…</p>}{error&&<p role="alert" className="text-rose-700">{error}</p>}<ul className="max-h-72 space-y-2 overflow-y-auto">{items.map(item=><li key={item.kind+item.id} className="flex items-center justify-between gap-3 rounded-lg bg-white p-3 text-sm"><span className="min-w-0 break-words">{item.name}</span><button type="button" className="btn-secondary shrink-0" disabled={busy} onClick={async()=>{setBusy(true);try{await api.archiveMaterial(item.kind,item.id,false);await load();onRestore();}catch(e){setError(errorMessage(e));}finally{setBusy(false);}}}>恢复到材料库</button></li>)}</ul>{!items.length&&!busy&&!error&&<p className="py-2 text-slate-600">暂无归档材料。</p>}</details>;
}
