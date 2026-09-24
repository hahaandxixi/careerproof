"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS, type Enterprise, type JobDraftResult, type JobOptions, type RequirementInput } from "@/lib/api/domain";
import { ErrorNotice } from "./AccessGate";

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
    return () => { current = false; };
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
    setDraftBusy(true); setDraftError(""); setAiDraft(null);
    try {
      const result = await api.draftJobRequirements({ description, externalAiConsent: draftConsent });
      setAiDraft(result); setDraftSource(description);
      setSelectedDraftRows(result.requirements.map((_, index) => index));
    } catch (reason) { setDraftError(errorMessage(reason)); }
    finally { setDraftBusy(false); }
  }
  function acceptDraft() {
    if (!aiDraft || description !== draftSource || selectedDraftRows.length === 0) return;
    setRequirements(aiDraft.requirements.filter((_, index) => selectedDraftRows.includes(index)).map(row => ({
      rawText: row.rawText, skillName: row.skillName, weight: row.weight, isRequired: row.isRequired,
      sourceQuote: row.sourceQuote, sourceStart: row.sourceStart, sourceEnd: row.sourceEnd,
    })));
    setAiDraft(null);
    setDraftError("");
  }
  function locateSource(start: number, end: number) {
    descriptionRef.current?.focus();
    descriptionRef.current?.setSelectionRange(start, end);
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (submitting.current) return;
    setError("");
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
    <div><Link className="text-sm text-indigo-600" href="/jobs/mine">← 我的岗位</Link><h1 className="mt-2 text-3xl font-bold">{jobId ? "编辑岗位" : "发布岗位"}</h1></div>
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {!jobId && <details className="panel" open={!organizations.length}>
      <summary className="cursor-pointer font-semibold">{organizations.length ? "创建另一个企业组织" : "先创建你的企业组织"}</summary>
      <p className="mt-2 text-sm text-slate-500">创建后你成为该组织的负责人。自建组织尚未经平台认证。</p>
      <form onSubmit={createOrganization} className="mt-4 space-y-3">
        <label className="block text-sm">企业名称<input className="field mt-1" required maxLength={200} value={organizationName} onChange={e => setOrganizationName(e.target.value)} /></label>
        <label className="block text-sm">企业说明<textarea className="field mt-1" maxLength={5000} value={organizationDescription} onChange={e => setOrganizationDescription(e.target.value)} /></label>
        {organizationError && <ErrorNotice message={organizationError} />}
        <button className="btn-secondary" disabled={organizationBusy}>{organizationBusy ? "创建中…" : "创建并选择企业"}</button>
      </form>
    </details>}
    <form onSubmit={submit} className="space-y-6">
      <fieldset disabled={busy || !organizations.length} className="space-y-6">
        <div className="panel grid gap-4 sm:grid-cols-2">
          <label className="text-sm">所属企业<select className="field mt-1" required disabled={!!jobId} value={enterpriseId} onChange={e => setEnterpriseId(e.target.value)}><option value="">请选择</option>{organizations.map(org => <option key={org.id} value={org.id}>{org.name}{org.isVerified ? " · 已认证" : " · 未认证"}</option>)}</select></label>
          <label className="text-sm">岗位名称<input className="field mt-1" required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label>
          <label className="text-sm">岗位方向<select className="field mt-1" value={category} onChange={e => setCategory(e.target.value)}>{Object.entries(CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="text-sm">工作城市<input className="field mt-1" maxLength={100} value={city} onChange={e => setCity(e.target.value)} placeholder="如：杭州 / 远程" /></label>
          <label className="text-sm">工作类型<select className="field mt-1" value={employmentType} onChange={e => setEmploymentType(e.target.value)}>{Object.entries(EMPLOYMENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="text-sm">岗位状态<select className="field mt-1" value={jobStatus} onChange={e => setJobStatus(e.target.value)}><option value="draft">保存草稿</option><option value="published">公开发布</option><option value="closed">关闭</option></select></label>
          <label className="text-sm sm:col-span-2">岗位描述<textarea ref={descriptionRef} className="field mt-1" rows={7} maxLength={20000} value={description} onChange={e => setDescription(e.target.value)} /></label>
        </div>
        <div className="panel space-y-4">
          <div><h2 className="font-semibold">AI 拆解岗位要求</h2><p className="mt-1 text-sm leading-7 text-slate-600">粘贴完整岗位描述（AI 拆解限 20–6000 字），AI 提取最多 12 条要求并附上原文定位。你可以逐条选择、修改，确认后才进入发布表单。</p></div>
          <label className="flex items-start gap-3 rounded-lg bg-indigo-50 p-3 text-xs leading-6 text-indigo-900"><input className="mt-1" type="checkbox" checked={draftConsent} onChange={event => setDraftConsent(event.target.checked)} /><span>同意将当前岗位描述发送给配置的模型进行拆解。生成草稿不会自动保存或发布岗位，模型调用可能产生费用。</span></label>
          <button type="button" className="btn-secondary" disabled={draftBusy || !draftConsent || description.trim().length < 20 || description.length > 6000} onClick={generateDraft}>{draftBusy ? "AI 正在拆解…" : "从描述生成 AI 草稿"}</button>
          {draftError && <p className="text-sm text-rose-700">{draftError}</p>}
          {aiDraft && <div className="space-y-3 rounded-lg border border-indigo-200 p-4"><p className="text-xs text-indigo-700">{aiDraft.model} 生成的待确认草稿 · {aiDraft.requirements.length} 条</p>{description !== draftSource && <p className="text-sm text-amber-700">岗位描述已修改，请重新生成草稿后再采纳，确保原文定位准确。</p>}{aiDraft.requirements.map((row, index) => <label key={`${row.sourceStart}-${index}`} className="flex gap-3 rounded-lg bg-slate-50 p-3 text-sm"><input type="checkbox" className="mt-1" checked={selectedDraftRows.includes(index)} onChange={event => setSelectedDraftRows(values => event.target.checked ? [...values, index] : values.filter(value => value !== index))} /><span className="min-w-0 flex-1"><strong>{row.skillName}</strong> · 权重 {row.weight}/5 · {row.isRequired ? "必要要求" : "加分项"}<span className="mt-1 block">{row.rawText}</span><span className="mt-1 block text-xs text-slate-500">原文：“{row.sourceQuote}”</span><button type="button" className="mt-1 text-xs text-indigo-700 underline" onClick={event => { event.preventDefault(); locateSource(row.sourceStart, row.sourceEnd); }}>定位原文</button></span></label>)}<button type="button" className="btn-secondary" disabled={description !== draftSource || selectedDraftRows.length === 0} onClick={acceptDraft}>确认选中要求并填入表单</button></div>}
        </div>
        <div className="panel space-y-4">
          <h2 className="text-lg font-semibold">岗位要求</h2><p className="text-sm leading-6 text-slate-500">每条要求单独填写技能名称和重要程度。可使用自定义技能；超出规则支持范围的技能会标注“暂未支持”，不按零分处理。</p>
          <datalist id="job-skills">{options?.skills.filter(skill => skill.category === category || skill.category === "other").map(skill => <option key={skill.name} value={skill.name} />)}</datalist>
          {requirements.map((row, index) => <div key={index} className="space-y-3 rounded-xl border border-slate-200 p-4">
            <div className="flex items-center justify-between"><span className="text-sm font-medium">要求 {index + 1}</span><button type="button" className="text-sm text-rose-600" onClick={() => setRequirements(value => value.filter((_, i) => i !== index))}>删除</button></div>
            <label className="block text-sm">要求说明<input className="field mt-1" required maxLength={2000} value={row.rawText} onChange={e => updateRequirement(index, { rawText: e.target.value })} placeholder="如：能用 Excel 进行数据整理和分析" /></label>
            <div className="grid items-end gap-3 sm:grid-cols-3">
              <label className="text-sm">技能名称<input className="field mt-1" list="job-skills" required maxLength={100} value={row.skillName} onChange={e => updateRequirement(index, { skillName: e.target.value })} placeholder="如：Excel" /></label>
              <label className="text-sm">重要程度<select className="field mt-1" value={row.weight} onChange={e => updateRequirement(index, { weight: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map(weight => <option key={weight} value={weight}>{weight} / 5</option>)}</select></label>
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
