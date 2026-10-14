"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { useAuth } from "./AuthProvider";

export default function DemoCaseImport({sample}:{sample:{resumeName:string;resumeFilename:string;projectName:string;projectFilename:string}}){
  const {user}=useAuth();const [busy,setBusy]=useState(false),[notice,setNotice]=useState("");const locked=useRef(false);
  if(user?.role!=="student")return null;
  async function run(){if(locked.current)return;locked.current=true;setBusy(true);setNotice("正在准备本地合成材料…");
    try{
      const [resumes,projects]=await Promise.all([api.listResumes(true),api.listProjects(true)]);
      const r=resumes.filter(v=>v.title===sample.resumeName),p=projects.filter(v=>v.name===sample.projectName);
      if(r.length>1||p.length>1)throw new Error("存在同名材料，请先在个人材料中核对；不会覆盖已有版本。");
      const rv=r[0]?.versions.filter(v=>v.originalFilename===sample.resumeFilename),pv=p[0]?.versions.filter(v=>v.originalFilename===sample.projectFilename);
      if(r[0]&&(!rv||rv.length!==1||rv[0].status!=="completed"))throw new Error("同名简历尚未解析成功或版本冲突，请先核对再重试。");
      if(p[0]&&p[0].description!=="合成静态测试作品，未执行，不代表本人贡献。")throw new Error("同名项目的说明不同，请核对；不会覆盖已有作品。");
      if(p[0]&&pv?.length&& (pv.length!==1||pv[0].status!=="completed"))throw new Error("项目正在解析或版本冲突，请稍后检查。");
      async function file(name:string,mime:string){const response=await fetch(`/demo-assets/cases/${encodeURIComponent(name)}`,{cache:"no-store"});if(!response.ok)throw new Error("测试文件暂不可用");return new File([await response.blob()],name,{type:mime});}
      // Fetch both before the first mutation. All writes use the current student's session.
      const [resumeFile,projectFile]=await Promise.all([file(sample.resumeFilename,"text/plain"),file(sample.projectFilename,"application/zip")]);
      if(!r[0])await api.uploadResume(sample.resumeName,resumeFile);
      else if(r[0].isArchived)await api.archiveMaterial("resume",r[0].id,false);
      const project=p[0]??await api.createProject({name:sample.projectName,description:"合成静态测试作品，未执行，不代表本人贡献。",requestId:crypto.randomUUID()});
      if(p[0]?.isArchived)await api.archiveMaterial("project",project.id,false);
      if(!pv?.length)await api.uploadProjectVersion(project.id,projectFile,crypto.randomUUID());
      setNotice("对应材料已保存到当前账号。到“个人材料”查看解析进度，待简历和项目均解析完成后，再按同编号选择；没有生成 AI 报告。");
    }catch(e){setNotice(errorMessage(e));}finally{locked.current=false;setBusy(false);}
  }
  return <div className="mt-3 space-y-2"><button type="button" disabled={busy} className="min-h-11 rounded-lg border border-indigo-200 px-3 py-2 text-sm text-indigo-700 disabled:opacity-50" onClick={()=>void run()}>{busy?"正在导入…":"导入这套材料到我的账号"}</button>{notice&&<><p role="status" className="text-xs leading-6 text-slate-600">{notice}</p><Link href="/portfolio" className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline">查看个人材料与解析进度 →</Link></>}</div>;
}
