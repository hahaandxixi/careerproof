"use client";
import { useState } from "react";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api/client";

export default function ApplicationSubmit({reportId}: {reportId:string}) {
  const [consent,setConsent] = useState(false), [busy,setBusy] = useState(false);
  const [notice,setNotice] = useState("");
  return <section className="panel space-y-3">
    <h2 className="font-semibold">向该岗位投递本份报告</h2>
    <p className="text-sm leading-6 text-slate-600">企业将能查看投递时固定的报告、代码引用片段，并下载本次简历原文件（可能含联系方式）。其他报告与其他版本不授权，不自动发送邮件或调用 AI。后续可撤回平台访问；已下载副本无法追回。</p>
    <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)} /><span>我已确认本份材料适合分享，同意向该岗位所属企业授权上述内容。</span></label>
    <button type="button" className="btn" disabled={!consent||busy} onClick={async()=>{setBusy(true);setNotice("");try{await api.createApplication(reportId);setNotice("已投递，可在“我的投递”查看企业回应与撤回授权。");}catch(e){setNotice(errorMessage(e));}finally{setBusy(false);}}}>{busy?"正在投递…":"确认投递"}</button>
    {notice&&<p role="status" className="text-sm text-indigo-700">{notice}</p>}
    <Link href="/applications" className="block text-sm text-indigo-700 underline">查看我的投递</Link>
  </section>;
}
