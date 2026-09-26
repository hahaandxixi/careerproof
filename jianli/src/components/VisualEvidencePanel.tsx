"use client";

import { useEffect, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api/client";
import type { VisualReview } from "@/lib/api/domain";

const LABELS: Record<string, string> = { architecture: "架构图", runtime: "运行界面", monitoring: "监控面板", document: "文档图片", other: "其他图片" };

export default function VisualEvidencePanel({ versionId }: { versionId: string }) {
  const [supported, setSupported] = useState(false);
  const [result, setResult] = useState<VisualReview | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  useEffect(() => {
    let current = true;
    api.getVisualReview(versionId).then(value => { if (current) { setSupported(true); setResult(value); setNote(value?.reviewerNote ?? ""); } })
      .catch(reason => { if (current && (!(reason instanceof ApiError) || reason.status !== 422)) setError(errorMessage(reason)); });
    return () => { current = false; };
  }, [versionId]);
  async function observe() {
    if (!consent || busy) return;
    setBusy(true); setError("");
    try { const value = await api.observeImage(versionId); setResult(value); setSelected(null); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function review(status: VisualReview["reviewStatus"]) {
    if (!result || busy) return;
    setBusy(true); setError("");
    try { setResult(await api.reviewVisual(result.id, status, note)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  if (!supported) return error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null;
  const region = selected == null ? null : result?.observations?.observations[selected]?.region;
  return <section className="panel space-y-4" aria-label="视觉内容观察">
    <div><h2 className="font-semibold">视觉内容观察</h2><p className="mt-2 text-sm leading-6 text-slate-600">本地 OCR 提取文字；视觉模型描述图中元素和位置。图片描述不参与实践评级，不能证明真实部署、持续运行、测试通过或本人贡献。</p></div>
    <div className="relative mx-auto max-w-3xl overflow-hidden rounded-lg border">
      {/* Authenticated, same-origin, normalized PNG; no remote image URL is accepted. */}
      <img src={`/backend/api/v1/project-versions/${versionId}/image`} alt="本人上传的图片作品，用于核对视觉描述" className="block h-auto w-full" />
      {region && <div aria-hidden="true" className="pointer-events-none absolute border-2 border-amber-500 bg-amber-200/20" style={{ left: `${region[0] * 100}%`, top: `${region[1] * 100}%`, width: `${(region[2] - region[0]) * 100}%`, height: `${(region[3] - region[1]) * 100}%` }} />}
    </div>
    {!result?.observations && <>
      {result?.status === "unavailable" && <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm">{result.failureKind === "provider_http_401" ? "视觉服务认证未通过，请联系管理员。" : "视觉模型不可用或输出未通过校验。"}本地 OCR 和原图仍可核对，未生成视觉结论。</p>}
      <label className="flex items-start gap-2 text-sm leading-6"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} className="mt-1" />我已检查图片，不含密钥、私人联系方式或未授权资料；允许将原图像素发送至智谱视觉模型。图片内容不会自动脱敏。</label>
      <button className="btn" disabled={!consent || busy} onClick={() => void observe()}>{busy ? "正在观察图片…" : "生成图片内容观察"}</button>
    </>}
    {result?.observations && <>
      <p className="text-xs text-slate-500">{LABELS[result.observations.image_kind]} · {result.model} · 本人核对：{({ pending: "待核对", accepted: "描述已采纳", rejected: "描述已驳回" })[result.reviewStatus]}{result.usage ? ` · 输入 ${result.usage.input_tokens ?? 0} / 输出 ${result.usage.output_tokens ?? 0} Tokens` : ""}</p>
      <ol className="space-y-3">{result.observations.observations.map((item, index) => <li key={index} className="rounded-lg bg-slate-50 p-3 text-sm leading-6"><p>{index + 1}. {item.description}</p>{item.visible_text && <p className="break-words">图中文字（模型读取）：{item.visible_text}</p>}<p className="text-slate-500">待核验：{item.needs_verification}</p><button className="mt-2 text-indigo-700 underline" onClick={() => setSelected(selected === index ? null : index)} aria-pressed={selected === index}>定位估计区域 {index + 1}</button></li>)}</ol>
      <p className="text-xs text-slate-500">区域是模型估计，未经过独立定位标注验收。本人采纳只记录描述核对，不是第三方认证，也不会提高等级。</p>
      <label className="block text-sm">核对说明<textarea className="field mt-2" value={note} maxLength={500} onChange={event => setNote(event.target.value)} /></label>
      <div className="flex flex-wrap gap-2">{(["accepted", "rejected", "pending"] as const).map(status => <button key={status} disabled={busy} className="btn-secondary" onClick={() => void review(status)}>{({ accepted: "采纳描述", rejected: "驳回描述", pending: "恢复待核对" })[status]}</button>)}</div>
    </>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
  </section>;
}
