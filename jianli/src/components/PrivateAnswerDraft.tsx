"use client";

import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { PrivateAnswerReferenceOption } from "@/lib/api/domain";
import {
  buildPrivateAnswerPreviewDocument, createPrivateAnswerSession, initialPrivateAnswerState,
  privateAnswerIsDirty, privateAnswerReferenceKey, privateAnswerSaveProblem, PRIVATE_ANSWER_MAX_TEXT,
} from "@/lib/private-answer-workflow";
import type { PrivateAnswerState } from "@/lib/private-answer-workflow";

export interface PrivateAnswerDraftProps {
  taskId: string;
  requirementId: string;
  requirementTitle: string;
  jobTitle: string;
  baseReportId: string;
  targetReportId: string | null;
  crossJob: boolean;
}

// 影响可选引用来源的目标绑定：只由这两个值决定；taskId 变化走整体重读不走局部刷新。
function privateAnswerBindingKey(props: Pick<PrivateAnswerDraftProps, "targetReportId" | "crossJob">): string {
  return `${props.targetReportId ?? ""}|${props.crossJob ? "cross-job" : "same-job"}`;
}

// 私人草稿会话不与分析轮询争代际：分析轮询的 setTask 只更新展示信息，effect 仅依赖 taskId；
// 身份切换由父组件 key 重挂载；隐藏/卸载在自身 effect 内 clear/dispose 并废弃迟到回执。
// clear 已使会话失活：恢复可见必须由本 effect 重新 activate 后再读取，旧DOM按钮无法复活会话。
export default function PrivateAnswerDraft(props: PrivateAnswerDraftProps) {
  const { taskId } = props;
  const [state, setState] = useState(initialPrivateAnswerState);
  const [previewOpen, setPreviewOpen] = useState(false);
  const sessionRef = useRef<ReturnType<typeof createPrivateAnswerSession> | null>(null);
  const infoRef = useRef(props);
  infoRef.current = props;
  const bindingRef = useRef(privateAnswerBindingKey(props));

  useEffect(() => {
    const session = createPrivateAnswerSession({
      getDraft: api.getAnswerDraft,
      saveDraft: api.saveAnswerDraft,
      listReferences: api.listAnswerDraftReferences,
      errorMessage,
    }, setState);
    sessionRef.current = session;
    session.activate();
    bindingRef.current = privateAnswerBindingKey(infoRef.current);
    void session.load(taskId, { crossJob: infoRef.current.crossJob, hasTargetReport: !!infoRef.current.targetReportId });
    const visibility = () => {
      if (document.visibilityState === "hidden") {
        session.clear();
        setPreviewOpen(false);
      } else {
        session.activate();
        void session.load(taskId, { crossJob: infoRef.current.crossJob, hasTargetReport: !!infoRef.current.targetReportId });
      }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => {
      session.dispose();
      sessionRef.current = null;
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [taskId]);

  // 目标绑定（目标报告/跨岗位）变化：只独立重验可选引用来源并关闭旧预览（阻止基于旧来源的确认复制），
  // 不重建草稿、不重置未存编辑；taskId 变化由上方 effect 整体重读，不需要这里的局部刷新。
  useEffect(() => {
    if (bindingRef.current === privateAnswerBindingKey(props)) return;
    bindingRef.current = privateAnswerBindingKey(props);
    setPreviewOpen(false);
    void sessionRef.current?.refreshReferences(taskId, {
      crossJob: infoRef.current.crossJob, hasTargetReport: !!infoRef.current.targetReportId,
    });
  }, [taskId, props.targetReportId, props.crossJob]);

  const session = () => sessionRef.current;
  const reload = () => {
    void session()?.load(taskId, { crossJob: infoRef.current.crossJob, hasTargetReport: !!infoRef.current.targetReportId });
  };
  return <PrivateAnswerDraftPanel
    state={state}
    requirementTitle={props.requirementTitle}
    jobTitle={props.jobTitle}
    baseReportId={props.baseReportId}
    targetReportId={props.targetReportId}
    crossJob={props.crossJob}
    previewOpen={previewOpen}
    onPreviewToggle={setPreviewOpen}
    onText={text => session()?.setText(text)}
    onToggle={option => session()?.toggleReference(option)}
    onRemove={key => session()?.removeSelection(key)}
    onSave={() => { void session()?.save(taskId); }}
    onReload={reload}
    onCompare={() => { void session()?.compareWithServer(taskId); }}
    onSaveOverServer={() => { void session()?.saveOverServer(taskId); }}
    onCopy={documentText => {
      void session()?.copy(documentText, text => navigator.clipboard.writeText(text));
    }}
  />;
}

export function PrivateAnswerDraftPanel(props: {
  state: PrivateAnswerState;
  requirementTitle: string;
  jobTitle: string;
  baseReportId: string;
  targetReportId: string | null;
  crossJob: boolean;
  previewOpen: boolean;
  onPreviewToggle: (open: boolean) => void;
  onText: (text: string) => void;
  onToggle: (option: PrivateAnswerReferenceOption) => void;
  onRemove: (key: string) => void;
  onSave: () => void;
  onReload: () => void;
  onCompare: () => void;
  onSaveOverServer: () => void;
  onCopy: (documentText: string) => void;
}) {
  const { state } = props;
  const dirty = privateAnswerIsDirty(state);
  const problem = privateAnswerSaveProblem(state.text, state.selected.length);
  const selectedKeys = new Set(state.selected.map(
    entry => privateAnswerReferenceKey(entry.reportId, entry.requirementId, entry.citationId)));
  const orphanSelections = state.selected.filter(
    entry => !state.options.some(option =>
      privateAnswerReferenceKey(option.reportId, option.requirementId, option.citationId)
      === privateAnswerReferenceKey(entry.reportId, entry.requirementId, entry.citationId)));
  const previewDocument = state.saved
    ? buildPrivateAnswerPreviewDocument({
      saved: state.saved,
      requirementTitle: props.requirementTitle, jobTitle: props.jobTitle,
      baseReportId: props.baseReportId, targetReportId: props.targetReportId,
    })
    : "";
  return <section className="panel space-y-4">
    <h2 className="text-lg font-semibold">私人回答草稿（仅本人可见）</h2>
    <p className="text-sm leading-6 text-slate-600">在这里整理自己的回答文字并选择可核验的报告引用。草稿只保存在你的账号下：不发送给企业、不进入投递快照，也不改变任务进度、评级或分析输入；草稿不是企业回复，也不代表任何通过结论。</p>
    <p className="text-sm text-slate-600">{state.saved
      ? `已保存：版本 ${state.saved.revision} · ${state.saved.updatedAt ?? "保存时间未知"} · ${dirty ? "有未保存修改" : "与已保存内容一致"}`
      : "尚未保存过草稿；首次保存从版本 0 开始。"}</p>
    {problem && <p role="alert" className="text-sm text-rose-700">{problem}</p>}
    {state.reading && <p role="status">正在读取已保存草稿…</p>}
    {state.saving && <p role="status">正在保存…</p>}
    {state.sourceCheck === "pending" && <p role="status">正在重新验证引用来源；完成后请基于刷新后的预览再确认复制。</p>}
    {state.sourceCheck === "failed" && <p role="alert" className="text-sm text-rose-700">引用来源重验失败，暂不能确认复制旧来源；可重试重验，或重读/保存以重新建立验证。</p>}
    {state.error && <p role="alert" className="text-sm text-rose-700">{state.error}</p>}
    {state.notice && <p role="status" className="text-sm leading-6 text-amber-800">{state.notice}</p>}
    <div className="space-y-2">
      <label className="text-sm font-medium" htmlFor="private-answer-text">回答草稿正文</label>
      {/* 保存期间允许继续编辑：只有读取期间暂时停用 */}
      <textarea id="private-answer-text" className="field min-h-32 w-full" aria-label="私人回答草稿正文"
        maxLength={PRIVATE_ANSWER_MAX_TEXT} value={state.text} disabled={state.reading}
        onChange={event => props.onText(event.target.value)}
        placeholder="写下你自己的回答草稿…（仅本人可见，不会发送给企业）" />
      <p className="text-xs text-slate-500">最多 {PRIVATE_ANSWER_MAX_TEXT} 字；换行按原样保存。清空内容也需要明确点击“保存草稿”才会替换服务器上的草稿。</p>
    </div>
    <fieldset disabled={state.reading} className="space-y-2 rounded-xl border border-indigo-200 p-3">
      <legend className="px-1 text-sm font-medium">从服务端可选引用中选择证据（原要求：{props.requirementTitle}）</legend>
      {state.options.length === 0 && <p className="text-xs leading-6 text-slate-600">本任务当前没有可选引用；没有草稿也可以先选择，保存时一并提交。</p>}
      <ul className="space-y-1">
        {state.options.map(option => {
          const key = privateAnswerReferenceKey(option.reportId, option.requirementId, option.citationId);
          return <li key={key} className="text-sm">
            <label className="flex items-start gap-2">
              <input type="checkbox" className="mt-1" checked={selectedKeys.has(key)} onChange={() => props.onToggle(option)} />
              <span className="min-w-0 flex-1 break-all">{option.reportKind === "base" ? "基准报告" : "目标报告"} {option.citationId} · {option.filePath} 第{option.lineStart}-{option.lineEnd}行{option.provenance === "reference" ? " · 第三方参考，不计入评级" : ""}</span>
            </label>
          </li>;
        })}
      </ul>
      {state.optionsNotice && <p className="text-xs leading-6 text-amber-800">{state.optionsNotice}</p>}
      {props.crossJob && <p className="text-xs leading-6 text-slate-600">跨岗位说明：企业问题与基准引用仍关联原岗位要求；目标报告只有包含本任务的原要求时才提供引用。</p>}
      {orphanSelections.length > 0 && <div className="space-y-1">
        <p className="text-xs font-medium text-rose-700">已保存但当前不可选的引用（来源关联已变化）：</p>
        <ul className="space-y-1">
          {orphanSelections.map(entry => {
            const key = privateAnswerReferenceKey(entry.reportId, entry.requirementId, entry.citationId);
            return <li key={key} className="text-sm text-rose-700"><span className="break-all">{entry.citationId} · 已失效{entry.filePath ? ` · ${entry.filePath}` : ""}，不作为有效来源复制</span>
              <button type="button" className="ml-2 text-xs text-indigo-700 underline" onClick={() => props.onRemove(key)}>移除</button>
            </li>;
          })}
        </ul>
      </div>}
      <p className="text-xs text-slate-500">最多选择 20 条引用；引用键由报告、要求与引用编号共同确定。</p>
    </fieldset>
    <div className="flex flex-wrap items-center gap-2">
      <button className="btn-secondary" disabled={state.saving || state.reading || !!problem} onClick={props.onSave}>保存草稿</button>
      <button className="btn-secondary" disabled={state.reading || state.saving} onClick={props.onReload}>重读已保存草稿</button>
    </div>
    {state.conflict && <div className="space-y-2 rounded-xl border border-amber-300 bg-amber-50 p-3">
      <p className="text-sm leading-6 text-amber-900">保存冲突：服务器上已有更新的版本。你的编辑已保留、未被覆盖；读取服务器版本仅作对照，不会自动替换。</p>
      {state.serverCopy && <div className="space-y-1">
        <p className="text-xs font-medium text-amber-900">服务器最新版本（仅对照，未覆盖你的编辑）：</p>
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-2 text-xs leading-6">{state.serverCopy.text === "" ? "（空）" : state.serverCopy.text}</pre>
        <p className="text-xs text-amber-900">版本 {state.serverCopy.revision} · {state.serverCopy.updatedAt}</p>
      </div>}
      <div className="flex flex-wrap gap-2">
        <button className="btn-secondary" disabled={state.comparing || state.saving} onClick={props.onCompare}>{state.comparing ? "正在读取…" : "读取服务器版本作对照"}</button>
        <button className="btn-secondary" disabled={state.saving || !state.serverCopy} onClick={props.onSaveOverServer}>以本人编辑重新保存（使用服务器版本号）</button>
      </div>
    </div>}
    <details open={props.previewOpen} onToggle={event => props.onPreviewToggle((event.target as HTMLDetailsElement).open)} className="rounded-xl border p-3">
      <summary className="cursor-pointer text-sm font-medium text-indigo-700">预览已保存草稿（先查看，再确认复制）</summary>
      <div className="mt-2 space-y-2">
        {(!state.saved || dirty) && <p role="status" className="text-sm leading-6 text-amber-800">{state.saved ? "有未保存编辑：预览与复制只包含已保存内容；请先保存草稿。" : "尚无已保存草稿；请先保存后再预览与复制。"}</p>}
        {state.saved && !dirty && <>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-2 text-xs leading-6">{previewDocument}</pre>
          <button className="btn-secondary" disabled={state.copying || state.sourceCheck !== "current"} onClick={() => props.onCopy(previewDocument)}>{state.copying ? "正在复制…" : "复制草稿（仅写入本机剪贴板）"}</button>
          <p className="text-xs leading-6 text-slate-500">复制只写入本机剪贴板，不会发送给企业，也不会改变任何投递或通知。</p>
        </>}
      </div>
    </details>
  </section>;
}
