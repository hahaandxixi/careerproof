"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS, type Enterprise, type JobDraftResult, type JobOptions, type RequirementInput } from "@/lib/api/domain";
import { ErrorNotice } from "./AccessGate";
import { combineDraftRequirements, createDraftRequestGuard, quoteStillMatches } from "@/lib/job-draft";

export default function JobForm({ jobId }: { jobId?: string }) {
  const router = useRouter();
  const [organizations, setOrganizations] = useState<Enterprise[]>([]);
  const [options, setOptions] = useState<JobOptions | null>(null);
  const [enterpriseId, setEnterpriseId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  const [draftConsent, setDraftConsent] = useState(false);
  const [draftBusy, setDraftBusy] = useState(false);
  const [draftError, setDraftError] = useState("");
  const draftRequests = useRef(createDraftRequestGuard());
  const [aiDraft, setAiDraft] = useState<JobDraftResult | null>(null);
  const [draftSource, setDraftSource] = useState("");
  const [selectedDraftRows, setSelectedDraftRows] = useState<number[]>([]);
  const [category, setCategory] = useState("software");
  const [city, setCity] = useState("不限");
  const [employmentType, setEmploymentType] = useState("internship");
  const [jobStatus, setJobStatus] = useState("draft");
  const [requirements, setRequirements] = useState<RequirementInput[]>([{ rawText: "", skillName: "", weight: 3, isRequired: true }]);
  const [organizationName, setOrganizationName] = useState("");
  const [organizationDescription, setOrganizationDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const originalRequirements = useRef("");
  const [organizationBusy, setOrganizationBusy] = useState(false);
  const [error, setError] = useState("");
  const [organizationError, setOrganizationError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const requestGuard = draftRequests.current;
    setDraftBusy(false);
    let current = true;
    setLoading(true); setError("");
    Promise.all([api.listEnterprises(), api.jobOptions(), jobId ? api.getJob(jobId) : Promise.resolve(null)])
      .then(([orgs, choices, job]) => {
        if (!current) return;
        setOrganizations(orgs); setOptions(choices); setEnterpriseId(job?.enterpriseId ?? orgs[0]?.id ?? "");
        if (job) {
          setTitle(job.title); setDescription(job.description); setCategory(job.category); setCity(job.city); setEmploymentType(job.employmentType); setJobStatus(job.status);
          const rows = job.requirements.map(({ rawText, skillName, weight, isRequired, sourceQuote, sourceStart, sourceEnd }) => ({ rawText, skillName, weight, isRequired, sourceQuote, sourceStart, sourceEnd }));
          setRequirements(rows); originalRequirements.current = JSON.stringify(rows);
        }
      }).catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; requestGuard.invalidate(); };
  }, [jobId, revision]);

  async function createOrganization(event: React.FormEvent) {
    event.preventDefault(); setOrganizationBusy(true); setOrganizationError("");
    try {
      const organization = await api.createEnterprise({ name: organizationName.trim(), description: organizationDescription.trim() });
      setOrganizations(value => [...value, organization]); setEnterpriseId(organization.id); setOrganizationName(""); setOrganizationDescription("");
    } catch (reason) { setOrganizationError(errorMessage(reason)); }
    finally { setOrganizationBusy(false); }
  }
  async function generateDraft() {
    if (!draftConsent || description.trim().length < 20 || description.length > 6000) return;
    if (draftBusy) return;
    const ticket = draftRequests.current.start();
    const source = description;
    setDraftBusy(true); setDraftError("");
    try {
      const result = await api.draftJobRequirements({ description, externalAiConsent: draftConsent });
      if (!draftRequests.current.accepts(ticket)) return;
      setAiDraft(result); setDraftSource(source);
      setSelectedDraftRows(result.requirements.map((_, index) => index));
    } catch (reason) { if (draftRequests.current.accepts(ticket)) setDraftError(errorMessage(reason)); }
    finally { if (draftRequests.current.isLatest(ticket)) setDraftBusy(false); }
  }
  function acceptDraft(mode: "append" | "replace") {
    if (!aiDraft || description !== draftSource || selectedDraftRows.length === 0) return;
    const existing = requirements.filter(r=>r.rawText.trim()||r.skillName.trim()).length;
    if (mode==="replace" && existing && !window.confirm(`将用选中的${selectedDraftRows.length}条草稿替换表单中现有${existing}条要求。现有编辑将被移除，是否继续？`)) return;
    try {
      setRequirements(combineDraftRequirements(requirements, aiDraft.requirements.filter((_,i)=>selectedDraftRows.includes(i)), mode));
      setAiDraft(null); setSelectedDraftRows([]); setDraftError("");
    } catch(reason) { setDraftError(errorMessage(reason)); }
  }
  function locateSource(start: number, end: number) {
    descriptionRef.current?.focus();
    descriptionRef.current?.setSelectionRange(start, end);
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (submitting.current) return;
    setError("");
    if (requirements.some(row=>!quoteStillMatches(description,row))) { setError("部分要求的原文关联已失效，请重新核对或取消原文关联。"); return; }
    if (!enterpriseId || !title.trim() || !requirements.length || requirements.some(r => !r.rawText.trim() || !r.skillName.trim())) {
      setError("请选择所属企业，填写岗位名称和至少一项完整的岗位要求。"); return;
    }
    submitting.current = true; setBusy(true);
    const fields = { title: title.trim(), description: description.trim(), category, city: city.trim() || "不限", employmentType, status: jobStatus, requirements: requirements.map(r => ({ ...r, rawText: r.rawText.trim(), skillName: r.skillName.trim() })) };
    try {
      const { requirements: updatedRequirements, ...metadata } = fields;
      const update = JSON.stringify(updatedRequirements) === originalRequirements.current ? metadata : fields;
      const job = jobId ? await api.updateJob(jobId, update) : await api.createJob({ ...fields, enterpriseId, companyName: organizations.find(item => item.id === enterpriseId)?.name ?? "" });
      router.push(`/jobs/${job.id}`); router.refresh();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { submitting.current = false; setBusy(false); }
  }
  function updateRequirement(index: number, patch: Partial<RequirementInput>) {
    setRequirements(value => value.map((row, i) => i === index ? { ...row, ...patch } : row));
  }
  if (loading) return <p className="py-12 text-center text-slate-500">正在加载企业与岗位配置…</p>;
  return <div className="space-y-6">
    <div><Link className="text-sm text-indigo-600" href="/jobs/mine">← 我的岗位</Link><h1 className="page-title mt-2">{jobId ? "编辑岗位" : "发布岗位"}</h1></div>
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {!jobId && <details className="panel" open={!organizations.length}>
      <summary className="cursor-pointer font-semibold">{organizations.length ? "创建另一个企业组织" : "先创建你的企业组织"}</summary>
      <p className="mt-2 text-sm text-slate-500">创建后你成为该组织的负责人。自建组织尚未经平台认证。</p>
      <form onSubmit={createOrganization} className="mt-4 space-y-3">
        <label className="form-label block">企业名称<input className="field mt-1" required maxLength={200} value={organizationName} onChange={e => setOrganizationName(e.target.value)} /></label>
        <label className="form-label block">企业说明<textarea className="field mt-1" maxLength={5000} value={organizationDescription} onChange={e => setOrganizationDescription(e.target.value)} /></label>
        {organizationError && <ErrorNotice message={organizationError} />}
        <button className="btn-secondary" disabled={organizationBusy}>{organizationBusy ? "创建中…" : "创建并选择企业"}</button>
      </form>
    </details>}
    <form onSubmit={submit} className="space-y-6">
      <fieldset disabled={busy || !organizations.length} className="space-y-6">
        <div className="panel grid gap-4 sm:grid-cols-2">
          <label className="form-label">所属企业<select className="field mt-1" required disabled={!!jobId} value={enterpriseId} onChange={e => setEnterpriseId(e.target.value)}><option value="">请选择</option>{organizations.map(org => <option key={org.id} value={org.id}>{org.name}{org.isVerified ? " · 已认证" : " · 未认证"}</option>)}</select></label>
          <label className="form-label">岗位名称<input className="field mt-1" required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label>
          <label className="form-label">岗位方向<select className="field mt-1" value={category} onChange={e => setCategory(e.target.value)}>{Object.entries(CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="form-label">工作城市<input className="field mt-1" maxLength={100} value={city} onChange={e => setCity(e.target.value)} placeholder="如：杭州 / 远程" /></label>
          <label className="form-label">工作类型<select className="field mt-1" value={employmentType} onChange={e => setEmploymentType(e.target.value)}>{Object.entries(EMPLOYMENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="form-label">岗位状态<select className="field mt-1" value={jobStatus} onChange={e => setJobStatus(e.target.value)}><option value="draft">保存草稿</option><option value="published">公开发布</option><option value="closed">关闭</option></select></label>
          <label className="form-label sm:col-span-2">岗位描述<textarea ref={descriptionRef} className="field mt-1" rows={5} maxLength={20000} value={description} onChange={e => {draftRequests.current.sourceChanged(); setDescription(e.target.value);}} /><span className="mt-1 block text-sm text-slate-600">{description.length} 字 · AI 提取要求支持20–6000字</span></label>
        </div>
        <details className="rounded-xl border border-slate-200 bg-white px-4"><summary className="cursor-pointer py-3 text-base font-medium text-indigo-700">从岗位描述提取要求</summary><div className="space-y-4 pb-4">
          <label className="flex items-start gap-3 rounded-lg bg-indigo-50 p-3 text-xs leading-6 text-indigo-900"><input className="mt-1" type="checkbox" checked={draftConsent} onChange={event => setDraftConsent(event.target.checked)} /><span>同意将当前岗位描述发送给配置的模型进行拆解。生成草稿不会自动保存或发布岗位，模型调用可能产生费用。</span></label>
          <button type="button" className="btn-secondary" disabled={draftBusy || !draftConsent || description.trim().length < 20 || description.length > 6000} onClick={generateDraft}>{draftBusy ? "正在提取…" : aiDraft ? "重新提取要求" : "提取要求草稿"}</button>
          {!draftBusy && (description.trim().length<20 || description.length>6000 || !draftConsent) && <p className="text-sm text-slate-600">{description.trim().length<20 ? "请先填写至少20字的岗位描述。" : description.length>6000 ? "岗位描述超过6000字，请精简后再提取。" : "请先确认上述外发范围。"}</p>}
          {draftError && <p className="text-sm text-rose-700">{draftError}</p>}
          {aiDraft && <div className="space-y-3 border-t border-slate-200 pt-4"><p className="text-sm text-slate-600">待确认草稿 · {aiDraft.requirements.length}条</p>
            {description !== draftSource && <p className="text-sm text-amber-800">岗位描述已修改。旧草稿仅供参考，请重新提取后再采纳。</p>}
            {aiDraft.requirements.map((row,index)=><div key={index} className="space-y-2 rounded-lg bg-slate-50 p-3">
              <div className="flex items-center justify-between"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selectedDraftRows.includes(index)} onChange={e=>setSelectedDraftRows(v=>e.target.checked?[...v,index]:v.filter(i=>i!==index))}/>要求{index+1}</label><button type="button" className="text-sm text-rose-700" onClick={()=>{setAiDraft(v=>v?{...v,requirements:v.requirements.filter((_,i)=>i!==index)}:v);setSelectedDraftRows(v=>v.filter(i=>i!==index).map(i=>i>index?i-1:i));}}>移除草稿</button></div>
              <label className="block text-sm">要求说明<input className="field mt-1" maxLength={2000} value={row.rawText} onChange={e=>setAiDraft(v=>v?{...v,requirements:v.requirements.map((r,i)=>i===index?{...r,rawText:e.target.value}:r)}:v)}/></label>
              <div className="grid gap-3 sm:grid-cols-3"><label className="text-sm">技能<input className="field mt-1" maxLength={100} value={row.skillName} onChange={e=>setAiDraft(v=>v?{...v,requirements:v.requirements.map((r,i)=>i===index?{...r,skillName:e.target.value}:r)}:v)}/></label><label className="text-sm">重要程度<select className="field mt-1" value={row.weight} onChange={e=>setAiDraft(v=>v?{...v,requirements:v.requirements.map((r,i)=>i===index?{...r,weight:Number(e.target.value)}:r)}:v)}>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n}/5</option>)}</select></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={row.isRequired} onChange={e=>setAiDraft(v=>v?{...v,requirements:v.requirements.map((r,i)=>i===index?{...r,isRequired:e.target.checked}:r)}:v)}/>必要要求</label></div>
              <details className="text-sm"><summary className="cursor-pointer text-indigo-700">原文依据与建议</summary><p className="mt-2">{row.sourceQuote}</p>{row.evidenceRequest&&<p>{row.evidenceRequest}</p>}{row.verificationQuestion&&<p>{row.verificationQuestion}</p>}<button type="button" disabled={description!==draftSource} className="min-h-10 text-indigo-700 underline" onClick={()=>locateSource(row.sourceStart,row.sourceEnd)}>定位原文</button></details>
            </div>)}
            <div className="flex flex-wrap gap-3"><button type="button" className="btn-secondary" disabled={description!==draftSource||!selectedDraftRows.length} onClick={()=>acceptDraft("append")}>追加选中要求</button><button type="button" className="min-h-11 text-sm text-slate-600 underline" disabled={description!==draftSource||!selectedDraftRows.length} onClick={()=>acceptDraft("replace")}>替换表单要求…</button></div>
          </div>}
        </div></details>
        <div className="panel space-y-4">
          <h2 className="section-title">岗位要求</h2><p className="text-sm leading-6 text-slate-500">每条要求单独填写技能名称和重要程度。可使用自定义技能；超出规则支持范围的技能会标注“暂未支持”，不按零分处理。</p>
          <datalist id="job-skills">{options?.skills.filter(skill => skill.category === category || skill.category === "other").map(skill => <option key={skill.name} value={skill.name} />)}</datalist>
          {requirements.map((row, index) => <div key={index} className="space-y-3 rounded-lg bg-slate-50 p-3 sm:p-4">
            <div className="flex items-center justify-between"><span className="text-sm font-medium">要求 {index + 1}</span><button type="button" className="text-sm text-rose-600" onClick={() => setRequirements(value => value.filter((_, i) => i !== index))}>删除</button></div>
            <label className="form-label block">要求说明<input className="field mt-1" required maxLength={2000} value={row.rawText} onChange={e => updateRequirement(index, { rawText: e.target.value })} placeholder="如：能用 Excel 进行数据整理和分析" /></label>
            <div className="grid grid-cols-2 items-end gap-3 sm:grid-cols-[minmax(0,1fr)_8rem_auto]">
              <label className="form-label">技能名称<input className="field mt-1" list="job-skills" required maxLength={100} value={row.skillName} onChange={e => updateRequirement(index, { skillName: e.target.value })} placeholder="如：Excel" /></label>
              <label className="form-label">重要程度<select className="field mt-1" value={row.weight} onChange={e => updateRequirement(index, { weight: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map(weight => <option key={weight} value={weight}>{weight} / 5</option>)}</select></label>
              <label className="flex items-center gap-2 py-3 text-sm"><input type="checkbox" checked={row.isRequired} onChange={e => updateRequirement(index, { isRequired: e.target.checked })} />必要要求</label>
            </div>
            {row.sourceQuote && <div className="rounded-lg bg-indigo-50 p-3 text-xs leading-6 text-indigo-900"><p>关联岗位原文：“{row.sourceQuote}”</p><div className="mt-1 flex gap-4"><button type="button" className="underline" onClick={() => locateSource(row.sourceStart ?? 0, row.sourceEnd ?? 0)}>定位原文</button><button type="button" className="underline" onClick={() => updateRequirement(index, { sourceQuote: null, sourceStart: null, sourceEnd: null })}>取消原文关联，改为人工要求</button></div></div>}
          </div>)}
          <button type="button" className="btn-secondary" disabled={requirements.length >= 50} onClick={() => setRequirements(value => [...value, { rawText: "", skillName: "", weight: 3, isRequired: true }])}>添加要求</button>
        </div>
        <button className="btn" disabled={busy || !organizations.length}>{busy ? "保存中…" : jobId ? "保存修改" : jobStatus === "published" ? "发布岗位" : "保存岗位"}</button>
      </fieldset>
    </form>
  </div>;
}
