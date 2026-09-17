"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS, type Enterprise, type JobOptions, type RequirementInput } from "@/lib/api/domain";
import { ErrorNotice } from "./AccessGate";

export default function JobForm({ jobId }: { jobId?: string }) {
  const router = useRouter();
  const [organizations, setOrganizations] = useState<Enterprise[]>([]);
  const [options, setOptions] = useState<JobOptions | null>(null);
  const [enterpriseId, setEnterpriseId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
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
          const rows = job.requirements.map(({ rawText, skillName, weight, isRequired }) => ({ rawText, skillName, weight, isRequired }));
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
          <label className="text-sm sm:col-span-2">岗位描述<textarea className="field mt-1" rows={5} maxLength={20000} value={description} onChange={e => setDescription(e.target.value)} /></label>
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
          </div>)}
          <button type="button" className="btn-secondary" disabled={requirements.length >= 50} onClick={() => setRequirements(value => [...value, { rawText: "", skillName: "", weight: 3, isRequired: true }])}>添加要求</button>
        </div>
        <button className="btn" disabled={busy || !organizations.length}>{busy ? "保存中…" : jobId ? "保存修改" : jobStatus === "published" ? "发布岗位" : "保存岗位"}</button>
      </fieldset>
    </form>
  </div>;
}
