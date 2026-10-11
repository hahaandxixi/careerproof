import { ApiError } from "./api/client";
import type { PrivateAnswerDraft, PrivateAnswerDraftReference, PrivateAnswerReferenceOption, PrivateAnswerSave } from "./api/domain";

export const PRIVATE_ANSWER_MAX_TEXT = 6000;
export const PRIVATE_ANSWER_MAX_REFERENCES = 20;

export type PrivateAnswerProvenance = "portfolio" | "reference" | null;

/** 选中引用条目：可来自服务端可选列表，也可来自已保存回执（可能已失效）。 */
export interface PrivateAnswerSelectionEntry {
  reportId: string;
  requirementId: string;
  citationId: string;
  reportKind: "base" | "target" | "saved";
  available: boolean;
  filePath: string | null;
  lineStart: number | null;
  lineEnd: number | null;
  provenance: PrivateAnswerProvenance;
  snippet: string | null;
}

/** 最近一次成功保存（或显式刷新读取）得到的基线。 */
export interface PrivateAnswerSavedBaseline {
  text: string;
  revision: number;
  updatedAt: string | null;
  references: PrivateAnswerDraftReference[];
}

export interface PrivateAnswerState {
  phase: "loading" | "ready";
  reading: boolean;
  text: string;
  selected: PrivateAnswerSelectionEntry[];
  saved: PrivateAnswerSavedBaseline | null;
  options: PrivateAnswerReferenceOption[];
  optionsNotice: string;
  saving: boolean;
  comparing: boolean;
  copying: boolean;
  // 已保存引用来源的可信度：current=服务端回执或重验已确认；pending=来源重验进行中；
  // failed=上次重验失败。仅 current 允许确认复制，防止绑定变化后把旧目标来源当有效证据。
  sourceCheck: "current" | "pending" | "failed";
  serverCopy: PrivateAnswerDraft | null;
  conflict: boolean;
  error: string;
  notice: string;
  // hidden/切身份清除的丢弃提示（固定文案，不含用户数据）：独立于 notice 生命周期，
  // 恢复 load 的读取中、成功、失败全程保持可见，不被 load 首段同步清掉的 notice 影响；
  // 再次编辑或显式保存/对照/复制时结束；重复 clear（无新丢弃）保留既有提示。
  lossNotice: string;
}

export const initialPrivateAnswerState: PrivateAnswerState = {
  phase: "loading", reading: false, text: "", selected: [], saved: null,
  options: [], optionsNotice: "", saving: false, comparing: false, copying: false,
  sourceCheck: "current", serverCopy: null, conflict: false, error: "", notice: "", lossNotice: "",
};

// clear 的固定文案（31号审查P1-1）：只携带"是否有未保存编辑"这一个布尔事实，不携带任何草稿内容。
export const PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE =
  "页面已隐藏或切换身份：私人草稿状态已清除，未保存的修改已丢弃（草稿没有发送给企业）；恢复可见后将重新读取已保存草稿。";
export const PRIVATE_ANSWER_CLEAR_CLEAN_NOTICE =
  "页面已隐藏或切换身份：私人草稿状态已清除；没有未保存的编辑，恢复可见后将重新读取。";

/** 引用键是三元组：两个报告出现相同 citationId 也不能合并。 */
export function privateAnswerReferenceKey(reportId: string, requirementId: string, citationId: string): string {
  return JSON.stringify([reportId, requirementId, citationId]);
}

export function privateAnswerIsDirty(state: PrivateAnswerState): boolean {
  if (!state.saved) return state.text !== "" || state.selected.length > 0;
  if (state.text !== state.saved.text) return true;
  const savedKeys = state.saved.references.map(r => privateAnswerReferenceKey(r.reportId, r.requirementId, r.citationId));
  const selectedKeys = state.selected.map(e => privateAnswerReferenceKey(e.reportId, e.requirementId, e.citationId));
  return savedKeys.length !== selectedKeys.length || savedKeys.some((key, i) => key !== selectedKeys[i]);
}

export function privateAnswerSaveProblem(text: string, referenceCount: number): string {
  if (text.length > PRIVATE_ANSWER_MAX_TEXT) return `草稿文字超过上限（${PRIVATE_ANSWER_MAX_TEXT}字），请删减后再保存。`;
  if (referenceCount > PRIVATE_ANSWER_MAX_REFERENCES) return `引用数量超过上限（${PRIVATE_ANSWER_MAX_REFERENCES}条），请先移除部分引用。`;
  return "";
}

/** 跨岗位目标报告没有原要求时，解释为何不能用其新要求回答原问题。 */
export function privateAnswerReferenceScopeNotice(input: {
  options: PrivateAnswerReferenceOption[]; crossJob: boolean; hasTargetReport: boolean;
}): string {
  if (input.crossJob && input.hasTargetReport && !input.options.some(option => option.reportKind === "target")) {
    return "当前目标岗位报告没有本任务的原要求条目：跨岗位的新要求不能用来回答原问题，因此目标报告没有可选引用。";
  }
  return "";
}

function selectionFromSaved(saved: PrivateAnswerDraft, options: PrivateAnswerReferenceOption[]): PrivateAnswerSelectionEntry[] {
  const kindByKey = new Map(options.map(option => [
    privateAnswerReferenceKey(option.reportId, option.requirementId, option.citationId), option.reportKind,
  ] as const));
  return saved.references.map(ref => ({
    reportId: ref.reportId,
    requirementId: ref.requirementId,
    citationId: ref.citationId,
    reportKind: kindByKey.get(privateAnswerReferenceKey(ref.reportId, ref.requirementId, ref.citationId)) ?? "saved",
    available: ref.available,
    filePath: ref.filePath ?? null,
    lineStart: ref.lineStart ?? null,
    lineEnd: ref.lineEnd ?? null,
    provenance: ref.provenance ?? null,
    snippet: ref.snippet ?? null,
  }));
}

/** 预览/复制文本只来自已保存回执（含服务端验证的可用 snippet），不伪造可选列表原文。 */
export function buildPrivateAnswerPreviewDocument(input: {
  saved: PrivateAnswerSavedBaseline;
  requirementTitle: string;
  jobTitle: string;
  baseReportId: string;
  targetReportId: string | null;
}): string {
  const { saved, requirementTitle, jobTitle, baseReportId, targetReportId } = input;
  const lines: string[] = [];
  lines.push("【私人回答草稿 · 仅供本人核对】");
  lines.push(`对应原要求：${requirementTitle}（${jobTitle}）`);
  lines.push("——草稿正文——");
  lines.push(saved.text === "" ? "（空）" : saved.text);
  const usable = saved.references.filter(ref => ref.available);
  lines.push("——引用来源（服务端验证）——");
  if (!usable.length) {
    lines.push("暂无有效引用。");
  } else {
    for (const ref of usable) {
      const kind = ref.reportId === targetReportId ? "目标报告" : ref.reportId === baseReportId ? "基准报告" : "报告";
      const location = ref.filePath ? ` ${ref.filePath} 第${ref.lineStart}-${ref.lineEnd}行` : "";
      const referenceMark = ref.provenance === "reference" ? "（第三方参考，不计入评级）" : "";
      lines.push(`- ${kind} ${ref.citationId}${location}${referenceMark}`);
      if (ref.snippet) lines.push(`  原文片段：${ref.snippet}`);
    }
  }
  const unavailable = saved.references.filter(ref => !ref.available);
  if (unavailable.length) {
    lines.push("——已失效引用（未作为有效来源复制）——");
    lines.push(`${unavailable.map(ref => ref.citationId).join("、")}：来源关联已变化，请重新核对后再选择。`);
  }
  lines.push("——保存信息——");
  lines.push(`保存版本：${saved.revision} · 保存时间：${saved.updatedAt ?? "未知"}`);
  lines.push("说明：本草稿仅保存在本人账号下，未发送给企业，也不代表企业回复或任何通过结论。");
  return lines.join("\n");
}

interface PrivateAnswerDependencies {
  getDraft(taskId: string): Promise<PrivateAnswerDraft | null>;
  saveDraft(taskId: string, payload: PrivateAnswerSave): Promise<PrivateAnswerDraft>;
  listReferences(taskId: string): Promise<PrivateAnswerReferenceOption[]>;
  errorMessage(error: unknown): string;
}

// 会话并发模型（对应Codex固定快照20261006三项实测复现的修复）：
// - 只有 clear/dispose 递增会话纪元并使全部在途回执失效；load/save/compare/copy 互不废弃对方，
//   各自用独立busy互斥防重复提交，回执只写自己负责的字段，busy由各自回执复位，不会搁浅。
// - clear 同时使会话失活：隐藏/切身份后旧按钮的 save/compare/copy/setText 全部拒绝，
//   只有当前身份/任务effect重新 activate 才恢复（DOM按钮不能复活失效会话）。
// - 丢弃提示（lossNotice，P1-1）：clear 按清除前状态布尔判定"是否真的丢弃了未保存编辑"，
//   只发布固定文案；该字段独立于 notice 生命周期——load 读取中/成功/失败全程不动它，
//   仅再次编辑（setText/toggleReference/removeSelection）或显式保存/对照/复制时结束；
//   无新丢弃的重复 clear（读取中/失败后/成功后再次隐藏）保留既有提示不抹去（38号审查）。
//   load/refreshReferences 与并发票据语义不受其影响。
// - 读取用编辑序号区分先后：读取发起之后的新输入（文字/引用选择）不被GET回执覆盖；
//   显式重读仍替换点击之前就存在的本地编辑。
// - 读取回执不降级基线：GET结果比已知已保存版本旧（如在途保存刚落账）时，不用它覆盖
//   text/selected/saved，避免在途save被reload后的旧GET回写。
// - 可选引用有独立票据（load与refreshReferences发起时都递增）：目标绑定变化只刷新
//   options/optionsNotice，最后发起者生效，不重置未存编辑、不惊动草稿字段。
// - 来源可信度（sourceCheck）：保存回执/读取回执/重验成功置 current（前提是发起后没有更新的
//   来源重验）；重验中 pending、失败后 failed 都禁止确认复制；重验成功会把不再出现在可选列表的
//   已保存引用降级为失效（保留身份/版本/原文，仅 available=false），预览与复制不再将其作为有效来源。
// - 来源代际（sourceRun）：来源新旧按发起顺序区分，与草稿revision无关。读取/保存回执若发起于
//   更近一次重验之前，不得恢复该重验判失效的引用available，也不得把sourceCheck改回current
//   （pending/failed门禁由较新重验决定）；revision前进、busy复位、编辑保护责任不受影响。
// - 保存回执同样只前进不降级：回执到达前已读到更新版本（另一窗口再写入）时保持新基线，
//   saving 仍由回执正常复位。
export function createPrivateAnswerSession(
  apiDeps: PrivateAnswerDependencies,
  publish: (state: PrivateAnswerState) => void,
) {
  let active = false;
  let epoch = 0;
  let editSeq = 0;
  let optionsRun = 0;
  // 来源代际：每次来源重验发起时递增。GET/PUT回执只携带发起时刻的来源可用度，
  // 若其后已有更新的重验，回执不得恢复该重验否决的引用，也不得改写其门禁。
  let sourceRun = 0;
  let appliedValidation: { run: number; optionKeys: Set<string> } | null = null;
  let state = initialPrivateAnswerState;
  const set = (patch: Partial<PrivateAnswerState>) => { state = { ...state, ...patch }; publish(state); };
  const live = (capturedEpoch: number) => active && capturedEpoch === epoch;
  const markEdit = () => { editSeq += 1; };

  function scopeOf(scope?: { crossJob: boolean; hasTargetReport: boolean }) {
    return scope ?? { crossJob: false, hasTargetReport: false };
  }

  // 发起于更近一次重验之前的回执可用度是旧视角：已被该重验否决的引用不得借回执复活；
  // 未被否决或本就失效的引用保持回执原状。revision/文字等其余字段责任不受影响。
  function referencesUnderNewerValidation(
    references: PrivateAnswerDraftReference[],
    capturedSourceRun: number,
  ): PrivateAnswerDraftReference[] {
    const validation = appliedValidation;
    if (!validation || validation.run <= capturedSourceRun) return references;
    return references.map(ref =>
      ref.available && !validation.optionKeys.has(privateAnswerReferenceKey(ref.reportId, ref.requirementId, ref.citationId))
        ? { ...ref, available: false }
        : ref);
  }

  async function load(taskId: string, scope?: { crossJob: boolean; hasTargetReport: boolean }): Promise<boolean> {
    if (!active || state.reading) return false;
    const capturedEpoch = epoch;
    const editMark = editSeq;
    const capturedSourceRun = sourceRun;
    const optionsTicket = ++optionsRun;
    set({ reading: true, error: "", notice: "", conflict: false, serverCopy: null });
    try {
      const [draft, options] = await Promise.all([apiDeps.getDraft(taskId), apiDeps.listReferences(taskId)]);
      if (!live(capturedEpoch)) return false;
      // 基线只前进不降级：读取结果比已知已保存版本旧时不覆盖草稿字段。
      const draftApplies = draft === null
        ? state.saved === null
        : state.saved === null || draft.revision >= state.saved.revision;
      const editsProtected = editSeq !== editMark;
      // 发起后已有更新的来源重验：来源可信度由该重验决定（pending/failed/current），本回执不改回current。
      const staleSources = capturedSourceRun !== sourceRun;
      const next: PrivateAnswerState = { ...state, phase: "ready", reading: false };
      if (!staleSources) next.sourceCheck = "current";
      if (optionsTicket === optionsRun) {
        next.options = options;
        next.optionsNotice = privateAnswerReferenceScopeNotice({ options, ...scopeOf(scope) });
      }
      if (draftApplies) {
        const references = draft ? referencesUnderNewerValidation(draft.references, capturedSourceRun) : [];
        next.saved = draft
          ? { text: draft.text, revision: draft.revision, updatedAt: draft.updatedAt, references }
          : null;
        if (!editsProtected) {
          next.text = draft?.text ?? "";
          next.selected = draft ? selectionFromSaved({ ...draft, references }, options) : [];
        }
      }
      if (editsProtected && !draftApplies) {
        next.notice = "读取完成：保留了你读取期间的新输入；本地已有更新的保存结果，未用读取结果覆盖。";
      } else if (editsProtected) {
        next.notice = "读取完成：保留了你读取期间的新输入。";
      } else if (!draftApplies) {
        next.notice = "读取完成：本地已有更新的保存结果，未用读取结果覆盖。";
      }
      state = next;
      publish(state);
      return true;
    } catch (error) {
      if (live(capturedEpoch)) set({ phase: "ready", reading: false, error: apiDeps.errorMessage(error) });
      return false;
    }
  }

  // 目标绑定（目标报告/跨岗位）变化后的独立来源重验：刷新options与scope提示，并把已保存
  // 引用中不再出现在可选列表的来源降级为失效（保留身份与版本，不删除）；重验期间与失败后
  // 禁止确认复制，防止把旧目标来源当有效证据。不动text/selected，保存期间也可安全调用。
  async function refreshReferences(
    taskId: string,
    scope?: { crossJob: boolean; hasTargetReport: boolean },
  ): Promise<boolean> {
    if (!active) return false;
    const capturedEpoch = epoch;
    const optionsTicket = ++optionsRun;
    const validationRun = ++sourceRun;
    set({ sourceCheck: "pending" });
    try {
      const options = await apiDeps.listReferences(taskId);
      if (!live(capturedEpoch) || optionsTicket !== optionsRun) return false;
      const optionKeys = new Set(options.map(option =>
        privateAnswerReferenceKey(option.reportId, option.requirementId, option.citationId)));
      appliedValidation = { run: validationRun, optionKeys };
      const patch: Partial<PrivateAnswerState> = {
        options,
        optionsNotice: privateAnswerReferenceScopeNotice({ options, ...scopeOf(scope) }),
        sourceCheck: "current",
      };
      if (state.saved) {
        patch.saved = {
          ...state.saved,
          references: state.saved.references.map(ref =>
            ref.available && !optionKeys.has(privateAnswerReferenceKey(ref.reportId, ref.requirementId, ref.citationId))
              ? { ...ref, available: false }
              : ref),
        };
      }
      set(patch);
      return true;
    } catch (error) {
      if (live(capturedEpoch) && optionsTicket === optionsRun) {
        set({ error: apiDeps.errorMessage(error), sourceCheck: "failed" });
      }
      return false;
    }
  }

  function setText(text: string) {
    if (!active) return;
    markEdit();
    set({ text, lossNotice: "" });
  }

  function toggleReference(option: PrivateAnswerReferenceOption) {
    if (!active) return;
    const key = privateAnswerReferenceKey(option.reportId, option.requirementId, option.citationId);
    const selected = state.selected.filter(
      entry => privateAnswerReferenceKey(entry.reportId, entry.requirementId, entry.citationId) !== key,
    );
    if (selected.length === state.selected.length) {
      selected.push({
        reportId: option.reportId, requirementId: option.requirementId, citationId: option.citationId,
        reportKind: option.reportKind, available: true,
        filePath: option.filePath ?? null, lineStart: option.lineStart ?? null, lineEnd: option.lineEnd ?? null,
        provenance: option.provenance ?? null, snippet: null,
      });
    }
    markEdit();
    set({ selected, lossNotice: "" });
  }

  function removeSelection(key: string) {
    if (!active) return;
    markEdit();
    set({
      selected: state.selected.filter(
        entry => privateAnswerReferenceKey(entry.reportId, entry.requirementId, entry.citationId) !== key,
      ),
      lossNotice: "",
    });
  }

  async function persist(taskId: string, expectedRevision: number, overServer: boolean): Promise<boolean> {
    if (!active || state.saving) return false;
    const problem = privateAnswerSaveProblem(state.text, state.selected.length);
    if (problem) { set({ error: problem, lossNotice: "" }); return false; }
    const payload: PrivateAnswerSave = {
      text: state.text,
      references: state.selected.map(entry => ({
        reportId: entry.reportId, requirementId: entry.requirementId, citationId: entry.citationId,
      })),
      expectedRevision,
    };
    const capturedEpoch = epoch;
    const capturedSourceRun = sourceRun;
    set({ saving: true, error: "", notice: "", lossNotice: "" });
    try {
      const saved = await apiDeps.saveDraft(taskId, payload);
      if (!live(capturedEpoch)) return false;
      // 回执只前进不降级：回执到达前已从服务器读到更新版本（如另一窗口已再写入）时，
      // 保持较新基线不动，但 saving 仍由本回执正常复位，读取期间的编辑不受影响。
      if (state.saved && saved.revision < state.saved.revision) {
        set({
          saving: false,
          notice: `保存回执迟到（版本 ${saved.revision}）：服务器已有更新版本 ${state.saved.revision}，已保留较新内容未回退；可重读已保存草稿作对照。`,
        });
        return true;
      }
      const staleSources = capturedSourceRun !== sourceRun;
      const patch: Partial<PrivateAnswerState> = {
        saving: false,
        saved: {
          text: saved.text,
          revision: saved.revision,
          updatedAt: saved.updatedAt,
          references: referencesUnderNewerValidation(saved.references, capturedSourceRun),
        },
        conflict: false,
        serverCopy: null,
        notice: overServer
          ? "已以本人编辑重新保存（使用服务器版本号）。"
          : `已保存版本 ${saved.revision} · ${saved.updatedAt}。`,
      };
      // 发起后已有更新的来源重验：其 pending/failed 门禁由该重验决定，本回执不改回current。
      if (!staleSources) patch.sourceCheck = "current";
      set(patch);
      return true;
    } catch (error) {
      if (!live(capturedEpoch)) return false;
      if (error instanceof ApiError && error.status === 409) {
        set({
          saving: false,
          conflict: true,
          error: "",
          notice: `${apiDeps.errorMessage(error)} 已保留你的编辑，未被覆盖。可读取服务器版本作对照；如确定以本人编辑为准，请再明确选择“以本人编辑重新保存”。`,
        });
      } else {
        set({ saving: false, error: apiDeps.errorMessage(error) });
      }
      return false;
    }
  }

  function save(taskId: string) {
    return persist(taskId, state.saved?.revision ?? 0, false);
  }

  // 仅在用户明确选择“以本人编辑重新保存”后才使用对照读到的服务器 revision。
  function saveOverServer(taskId: string) {
    if (!state.conflict || !state.serverCopy) return Promise.resolve(false);
    return persist(taskId, state.serverCopy.revision, true);
  }

  async function compareWithServer(taskId: string): Promise<boolean> {
    if (!active || state.comparing) return false;
    const capturedEpoch = epoch;
    set({ comparing: true, error: "", lossNotice: "" });
    try {
      const draft = await apiDeps.getDraft(taskId);
      if (!live(capturedEpoch)) return false;
      if (draft === null) {
        set({ comparing: false, notice: "服务器上尚无已保存草稿；你的编辑仍保留，未被覆盖。" });
        return true;
      }
      set({
        comparing: false,
        serverCopy: draft,
        notice: "已读取服务器版本作对照；未覆盖你的编辑。要以服务器为准请点“重读已保存草稿”，要以本人编辑为准请明确选择重新保存。",
      });
      return true;
    } catch (error) {
      if (live(capturedEpoch)) set({ comparing: false, error: apiDeps.errorMessage(error) });
      return false;
    }
  }

  async function copy(documentText: string, write: (text: string) => Promise<void>): Promise<boolean> {
    if (!active || state.copying) return false;
    // 来源重验期间或失败后，不得基于旧预览确认复制；成功后失效引用由预览文档排除。
    if (state.sourceCheck === "pending") {
      set({ notice: "正在重新验证引用来源；完成后请基于刷新后的预览再确认复制。", lossNotice: "" });
      return false;
    }
    if (state.sourceCheck === "failed") {
      set({ notice: "引用来源重验失败，暂不能确认复制旧来源；可重试重验，或重读/保存以重新建立验证。", lossNotice: "" });
      return false;
    }
    if (!state.saved) { set({ notice: "尚无已保存草稿可复制；请先保存。", lossNotice: "" }); return false; }
    if (privateAnswerIsDirty(state)) {
      set({ notice: "有未保存编辑：预览与复制只包含已保存内容；请先保存草稿，再复制。", lossNotice: "" });
      return false;
    }
    // 剪贴板写入不参与任何代际：本地复制不得废弃仍在途的保存/读取回执。
    const capturedEpoch = epoch;
    set({ copying: true, error: "", notice: "", lossNotice: "" });
    try {
      await write(documentText);
      if (!live(capturedEpoch)) return false;
      set({ copying: false, notice: "已复制到本机剪贴板；本草稿没有发送给企业。" });
      return true;
    } catch (error) {
      if (!live(capturedEpoch)) return false;
      set({ copying: false, error: `复制失败：${apiDeps.errorMessage(error)}；可重试或手动选择文本复制。` });
      return false;
    }
  }

  return {
    activate() { active = true; },
    clear() {
      // hidden/切身份：按清除前的本地状态判定是否真的存在未保存编辑（布尔驱动固定文案，
      // 不携带任何草稿内容或身份数据）；丢弃事实写入独立的 lossNotice，恢复 load 读取中/
      // 成功/失败全程保持可见（P1-1：此前该声明被恢复 load 首段同步清空，用户永远看不到）。
      // 第二次 clear（读取中/失败后/成功后再次隐藏，此时状态已干净、无新丢弃）不得抹去
      // 仍然存活的 lossNotice——提示生命周期只由再次编辑或显式保存/对照/复制结束（38号审查）。
      const hadUnsaved = privateAnswerIsDirty(state);
      const carriedLossNotice = state.lossNotice;
      active = false;
      ++epoch;
      appliedValidation = null;
      state = {
        ...initialPrivateAnswerState,
        phase: "ready",
        notice: hadUnsaved ? PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE : PRIVATE_ANSWER_CLEAR_CLEAN_NOTICE,
        lossNotice: hadUnsaved ? PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE : carriedLossNotice,
      };
      publish(state);
    },
    dispose() { active = false; ++epoch; },
    load,
    refreshReferences,
    setText,
    toggleReference,
    removeSelection,
    save,
    saveOverServer,
    compareWithServer,
    copy,
  };
}
