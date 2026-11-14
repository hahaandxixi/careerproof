"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, errorMessage } from "@/lib/api/client";
import type { InterviewSession, PracticeTurn } from "@/lib/api/domain";
import { displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import {
  canSubmit, consentItems, draftKey, newClientToken, openTurn, practiceStatusLabel, practiceTurnSources, selectedPracticeTurn,
  canRetryFeedback, feedbackStatusLabel, generationPending, questionRetryNote, savedSubmission, summaryLine, tokenKey, turnLabel, turnNotice, visibleSummaryNextStep,
} from "@/lib/interview-practice";
import { useAuth } from "./AuthProvider";
import { ErrorNotice } from "./AccessGate";
import EvidenceSnippet from "./EvidenceSnippet";
import styles from "./InterviewPractice.module.css";

const MAX_ANSWER = 4000;

function SummaryIssues({ lines, visibleCount }: { lines: string[]; visibleCount: number }) {
  const remaining = lines.slice(visibleCount);
  return <>
    <ul>{lines.slice(0, visibleCount).map((line, index) => <li key={index}>{line}</li>)}</ul>
    {remaining.length > 0 && <details>
      <summary>查看其余 {remaining.length} 条（共 {lines.length} 条）</summary>
      <ul>{remaining.map((line, index) => <li key={index}>{line}</li>)}</ul>
    </details>}
  </>;
}

export default function InterviewPractice({ id }: { id: string }) {
  const { user, status } = useAuth();
  if (status === "loading") return <p className={styles.loading}>正在确认账号…</p>;
  return <PracticeWorkspace key={`${user?.id ?? "anonymous"}:${id}`} id={id} userId={user?.id} />;
}

function PracticeWorkspace({ id, userId }: { id: string; userId?: string }) {
  const router = useRouter();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [progressError, setProgressError] = useState("");
  const [notice, setNotice] = useState("");
  const [answer, setAnswer] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState<"start" | "restart" | number | null>(null);
  const [feedbackReadTurn, setFeedbackReadTurn] = useState<number | null>(null);
  const [selectedTurnIndex, setSelectedTurnIndex] = useState<number | null>(null);
  const draftKeyRef = useRef("");
  const active = useRef(false);

  const load = useCallback(async () => {
    try {
      const next = await api.getInterviewSession(id);
      if (active.current) {
        setSession(next);
        setLoadError("");
        setProgressError("");
        setFeedbackReadTurn(null);
      }
      return next;
    } catch (error) {
      if (active.current) {
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) setSession(null);
        setLoadError(errorMessage(error));
      }
      return null;
    } finally {
      if (active.current) setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    active.current = true;
    void load();
    return () => { active.current = false; };
  }, [load]);

  const pending = generationPending(session?.questionTask) || Boolean(session?.turns.some(turn => generationPending(turn.feedbackTask)));
  useEffect(() => {
    if (!pending || busy !== null) return;
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    const read = async () => {
      try {
        const next = await api.getInterviewSession(id);
        if (!current) return;
        setSession(next);
        setLoadError("");
        setProgressError("");
      } catch (error) {
        if (current && error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          setSession(null);
          setLoadError(errorMessage(error));
          return;
        }
        if (current) setProgressError(`暂未读取到练习进度。${errorMessage(error)}`);
      }
      if (current) timer = setTimeout(read, 1500);
    };
    timer = setTimeout(read, 1000);
    return () => { current = false; clearTimeout(timer); };
  }, [busy, id, pending]);

  const current = openTurn(session);
  useEffect(() => {
    if (!userId || !session || !current) return;
    const key = draftKey(userId, session.id, current.turnIndex);
    if (draftKeyRef.current === key) return;
    draftKeyRef.current = key;
    try { setAnswer(window.sessionStorage.getItem(key) ?? ""); } catch { setAnswer(""); }
  }, [userId, session, current]);

  const updateAnswer = (value: string) => {
    setAnswer(value);
    if (!userId || !session || !current) return;
    try { window.sessionStorage.setItem(draftKey(userId, session.id, current.turnIndex), value); } catch { /* private mode */ }
  };

  const start = async () => {
    setBusy("start");
    setActionError("");
    setNotice("");
    try {
      const next = await api.startInterviewSession(id, consent || Boolean(session?.consentAt));
      setSession(next);
    } catch (error) {
      setActionError(errorMessage(error));
      const latest = await load();
      if (latest?.turns.length) setSession(latest);
    } finally {
      setBusy(null);
    }
  };

  const submit = async (turn: PracticeTurn) => {
    if (!userId || !session) return;
    const text = answer.trim();
    if (!text) { setActionError("请先输入回答"); return; }
    const key = tokenKey(userId, session.id, turn.turnIndex);
    let token = "";
    try { token = window.sessionStorage.getItem(key) || ""; } catch { /* private mode */ }
    if (!token) { token = newClientToken(); try { window.sessionStorage.setItem(key, token); } catch { /* private mode */ } }
    setBusy(turn.turnIndex);
    setActionError("");
    setNotice("正在提交回答…");
    const clearSavedDraft = () => {
      try {
        window.sessionStorage.removeItem(draftKey(userId, session.id, turn.turnIndex));
        window.sessionStorage.removeItem(key);
      } catch { /* private mode */ }
      if (active.current) setAnswer("");
    };
    try {
      const next = await api.submitInterviewAnswer(session.id, turn.turnIndex, { answerText: text, clientToken: token });
      if (!active.current) return;
      setSession(next);
      if (savedSubmission(next, turn.turnIndex, text)) {
        clearSavedDraft();
        setNotice("");
      } else {
        setNotice("已保留你的输入，请核对服务器保存的回答。");
      }
    } catch (error) {
      const latest = await load();
      if (!active.current) return;
      const saved = savedSubmission(latest, turn.turnIndex, text);
      if (saved) {
        clearSavedDraft();
        setNotice(saved.feedback ? "已读取保存的点评。" : "");
      } else {
        setActionError(errorMessage(error));
        setNotice(latest ? "未确认这次回答已保存，输入仍保留。" : "暂时无法核对保存状态，输入仍保留。");
      }
    } finally {
      setBusy(null);
    }
  };

  const restartPractice = async () => {
    if (!session) return;
    setBusy("restart");
    setActionError("");
    try {
      const { session: next } = await api.createInterviewSession(session.reportId, { requirementId: session.requirementId, restart: true });
      if (active.current) router.push(`/interview/${next.id}`);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const retry = async (turn: PracticeTurn) => {
    setBusy(turn.turnIndex);
    setActionError("");
    setNotice("正在重新生成点评…");
    try {
      const next = await api.retryInterviewFeedback(session!.id, turn.turnIndex);
      if (active.current) {
        setSession(next);
        setFeedbackReadTurn(null);
      }
    } catch {
      if (!active.current) return;
      setFeedbackReadTurn(turn.turnIndex);
      await load();
    } finally {
      if (active.current) {
        setNotice("");
        setBusy(null);
      }
    }
  };

  if (loading) return <p className={styles.loading}>正在读取练习…</p>;
  if (loadError && !session) return <ErrorNotice message={loadError} retry={() => void load()} />;
  if (!session) return <ErrorNotice message="练习不存在或无权访问" retry={() => void load()} />;

  const reportHref = `/reports/${session.reportId}#requirement-${session.requirementId}`;
  const jobTitle = displayJobTitle(session.jobTitle, session.jobId);
  const turn = selectedPracticeTurn(session, selectedTurnIndex);
  const summaryNextStep = visibleSummaryNextStep(session.summary, turn);
  const isBusy = !!turn && busy === turn.turnIndex;
  const busyIdle = busy === null;
  const knowledgeOutdated = Boolean(session.knowledgeOutdated);

  return <div className={styles.page}>
    {loadError && <ErrorNotice message={loadError} retry={() => void load()} />}
    <header className={styles.head}>
      <div className={styles.titleRow}>
        <h1 className={styles.title}>模拟面试</h1>
        <span className={styles.status}>{practiceStatusLabel(session.status)}</span>
      </div>
      <div className={styles.requirement}>
        <span>{jobTitle ? `${jobTitle} · 本项岗位要求` : "本项岗位要求"}</span>
        <strong>{session.requirementTitle || session.skill}</strong>
      </div>
      <Link className={styles.headLink} href={reportHref}>回到原报告定位这项要求 →</Link>
    </header>

    {session.turns.length > 1 && <div className={styles.turnTrack} role="group" aria-label="练习轮次">
      {session.turns.map(item => <button type="button" key={item.turnIndex} aria-pressed={item === turn}
        onClick={() => setSelectedTurnIndex(item === session.turns.at(-1) || item === current ? null : item.turnIndex)}>
        <strong>第 {item.turnIndex + 1} 轮</strong><span>{item.state === "question" ? "待回答" : feedbackStatusLabel(item)}</span>
      </button>)}
    </div>}

    <div className={styles.layout}>
      <div className={styles.main}>
        {progressError && <ErrorNotice message={progressError} retry={() => void load()} />}
        {actionError && <ErrorNotice message={actionError} />}
        {notice && <p role="status" className={styles.notice} data-tone="working">{notice}</p>}

        {knowledgeOutdated && <section className={styles.consent} aria-labelledby="practice-knowledge-updated">
          <h2 id="practice-knowledge-updated">知识依据已更新，请重新开始练习</h2>
          <p>可以继续查看已保存的题目、回答和点评。开始新练习后，系统会用更新后的知识出题。</p>
          <div className={styles.actions}>
            <button type="button" className="btn" disabled={!busyIdle} onClick={() => void restartPractice()}>
              {busy === "restart" ? "正在创建新练习…" : "重新开始练习"}
            </button>
            <button type="button" className="btn-quiet" disabled={!busyIdle} onClick={() => void load()}>读取当前保存状态</button>
          </div>
        </section>}

        {session.status === "draft" && <section className={styles.consent} aria-labelledby="practice-consent">
          <h2 id="practice-consent">开始前确认发送范围</h2>
          <p>生成首问和点评需要调用模型。本次只会发送以下内容；不发送简历全文、私人回答草稿或投递记录。</p>
          <ul className={styles.consentList}>
            {consentItems(session).map(item => <li key={item}>{item}</li>)}
          </ul>
          <label className={styles.check}>
            <input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />
            <span>我已了解并同意把上述内容发送给模型，用于生成这一项要求的练习问题与点评。</span>
          </label>
          <div className={styles.actions}>
            <button type="button" className="btn" disabled={!consent || !busyIdle || knowledgeOutdated} onClick={() => void start()}>
              {busy === "start" ? "正在生成首问…" : "同意并生成首问"}
            </button>
            <span className={styles.hint}>不同意也可以返回报告继续核对材料，不会产生模型调用。</span>
          </div>
          {session.failureReason && <p className={styles.notice} data-tone="failed">{session.failureReason}</p>}
        </section>}

        {generationPending(session.questionTask) && <p role="status" className={styles.notice} data-tone="working">
          {session.questionTask?.status === "running" ? "正在生成首问" : "已保存发送确认，等待生成首问"}
        </p>}

        {!!questionRetryNote(session) && <section className={styles.consent} aria-labelledby="practice-question-retry">
          <h2 id="practice-question-retry">首问还没有生成</h2>
          <p>{questionRetryNote(session)}</p>
          <p className={styles.hint}>发送范围已经确认并记录，重试只会重新生成首问，不会改动报告判断、技能状态或投递快照。</p>
          <div className={styles.actions}>
            <button type="button" className="btn" disabled={!busyIdle || knowledgeOutdated} onClick={() => void start()}>
              {busy === "start" ? "正在重新生成首问…" : "重试生成首问"}
            </button>
            <button type="button" className="btn-quiet" disabled={!busyIdle} onClick={() => void load()}>读取保存状态</button>
          </div>
        </section>}

        {turn && <article key={turn.turnIndex} className={styles.turn} aria-label={turnLabel(turn)}>
          <div className={styles.turnHead}>
            <h2>第 {turn.turnIndex + 1} 轮{turn.kind === "follow_up" ? " · 追问" : " · 首问"}</h2>
            <span className={styles.turnState}>{turn.state === "question" ? "待回答" : "回答已保存"}</span>
          </div>
          <p className={styles.question}>{turn.question}</p>
          {!!turn.focus && <p className={styles.focus}>关注点：{turn.focus}</p>}

          {turn === current && <div>
            <label className="text-sm font-medium" htmlFor={`practice-answer-${turn.turnIndex}`}>你的回答</label>
            <textarea id={`practice-answer-${turn.turnIndex}`} className={styles.answerBox} value={answer} maxLength={MAX_ANSWER}
              placeholder="用具体例子说明你的做法、取舍和验证方式。可以分点写。" disabled={!canSubmit(session, turn) || isBusy}
              onChange={event => updateAnswer(event.target.value)} />
            <div className={styles.footerRow}>
              <span className={styles.counter}>{answer.length} / {MAX_ANSWER} 字</span>
              <div className={styles.actions}>
                <button type="button" className="btn" disabled={isBusy || !answer.trim() || knowledgeOutdated} onClick={() => void submit(turn)}>
                  {isBusy ? "正在提交回答…" : "提交回答并获取点评"}
                </button>
              </div>
            </div>
            <p className={styles.hint}>未提交的内容会在这台设备上按账号暂存；提交后回答立即保存，模型失败也不会丢失。</p>
          </div>}

          {!!turn.answerText && <details className={styles.savedDetails} open={turn.feedback ? undefined : true}>
            <summary>查看已保存的回答</summary>
            <div className={styles.answerSaved}>{turn.answerText}</div>
          </details>}

          {turn.state !== "question" && !turn.feedback && <div className={styles.actions}>
            <span className={styles.notice} data-tone={turn.state === "failed" ? "failed" : "info"}>{feedbackReadTurn === turn.turnIndex ? "暂时无法确认点评重试结果，请读取保存状态。" : turnNotice(turn)}</span>
            {feedbackReadTurn !== turn.turnIndex && canRetryFeedback(turn) && <button type="button" className="btn-secondary" disabled={!busyIdle || knowledgeOutdated} onClick={() => void retry(turn)}>{isBusy ? "正在重试…" : "重试点评"}</button>}
            <button type="button" className="btn-quiet" disabled={!busyIdle} onClick={() => void load()}>读取保存状态</button>
          </div>}

          {turn.feedback && <section className={styles.feedback} aria-label="本轮点评">
            <h3>回答诊断</h3>
            <div className={styles.diagnosis}>
              {!!turn.feedback.covered.length && <div className={styles.feedbackBlock} data-kind="covered"><h4>✓ 已讲清 · {turn.feedback.covered.length}</h4><ul>{turn.feedback.covered.map((line, index) => <li key={index}>{line}</li>)}</ul></div>}
              {!!turn.feedback.missing.length && <div className={styles.feedbackBlock} data-kind="missing"><h4>○ 待补充 · {turn.feedback.missing.length}</h4><ul>{turn.feedback.missing.map((line, index) => <li key={index}>{line}</li>)}</ul></div>}
              {!!turn.feedback.inconsistent.length && <div className={styles.feedbackBlock} data-kind="inconsistent">
                <h4>! 需修正 · {turn.feedback.inconsistent.length}</h4>
                <ul>{turn.feedback.conflictDetails?.length ? turn.feedback.conflictDetails.map((conflict, index) => {
                  const file = turn.feedback?.citations.find(item => item.citationId === conflict.basisId);
                  const principle = turn.feedback?.knowledge.find(item => item.knowledgeId === conflict.basisId);
                  return <li key={index}>
                    <q>{conflict.answerQuote}</q> {conflict.reason}
                    {file && <p>{file.filePath.split("/").pop()} · 第 {file.lineStart}–{file.lineEnd} 行</p>}
                    {principle && <p>{principle.title}</p>}
                  </li>;
                }) : turn.feedback.inconsistent.map((line, index) => <li key={index}>{line}</li>)}</ul>
              </div>}
            </div>
            {!turn.feedback.covered.length && !turn.feedback.inconsistent.length && !turn.feedback.missing.length &&
              <p className={styles.empty}>本轮点评没有保存诊断条目。</p>}
            {!!turn.feedback.reviewSuggestion && <div className={styles.suggestion}><strong>改进建议：</strong>{turn.feedback.reviewSuggestion}</div>}
          </section>}
          {current && turn !== current && <div className={styles.actions}>
            <button type="button" className="btn" onClick={() => setSelectedTurnIndex(null)}>继续回答第 {current.turnIndex + 1} 轮</button>
          </div>}
        </article>}

        {session.summary && <section className={styles.summary} aria-label="练习小结">
          <details className={styles.summaryDetails}>
            <summary>查看整场练习小结</summary>
            <div>
              <p className={styles.summaryNote}>{summaryLine(session.summary)}</p>
              {session.summary.issueTrail ? <>
                {session.summary.issueTrail.length ? <ul className={styles.issueTrail}>
                  {session.summary.issueTrail.map(issue => {
                    const originIndex = Number(issue.origin.issueId.split(":")[0]);
                    const original = session.turns.find(turn => turn.turnIndex === originIndex);
                    const followUp = session.turns.find(turn => turn.turnIndex === issue.turnIndex);
                    const sourceTurn = followUp ?? original;
                    const state = issue.answerQuote ? "covered" : issue.kind;
                    return <li key={issue.issueId}><details>
                      <summary><strong>{issue.origin.point || issue.origin.text}</strong>
                        <span>第 {originIndex + 1} 轮{issue.origin.issueId.includes(":inconsistent:") ? "需修正" : "缺口"}{issue.turnIndex != null && issue.turnIndex !== originIndex &&
                          ` → 第 ${issue.turnIndex + 1} 轮${issue.answerQuote ? "补答" : "仍待核对"}`}</span>
                        <span className={styles.issueStatus} data-kind={state} data-resolved={!!issue.answerQuote}>{issue.answerQuote ? "✓ 已修正" : issue.kind === "inconsistent" ? "! 需修正" : "○ 仍待补"}</span>
                      </summary>
                      <div className={styles.issueDetails}>
                        {(issue.answerQuote || issue.text !== issue.origin.text) && <p><strong>第 {originIndex + 1} 轮原点评</strong><br />{issue.origin.text}</p>}
                        {!issue.answerQuote && issue.conflict && <><p>第 {(issue.turnIndex ?? originIndex) + 1} 轮回答原话</p><blockquote>{issue.conflict.answerQuote}</blockquote></>}
                        {!issue.answerQuote && <p>{issue.text}</p>}
                        {issue.answerQuote && <><p>补答原话</p><blockquote>{issue.answerQuote}</blockquote></>}
                        {(issue.origin.questionQuote || original?.question) && <><p>第 {originIndex + 1} 轮题目</p><blockquote>{issue.origin.questionQuote || original?.question}</blockquote></>}
                        {sourceTurn?.feedback && <PracticeSources session={session} turn={sourceTurn} compact
                          basisId={issue.answerQuote ? undefined : issue.conflict?.basisId} />}
                      </div>
                    </details></li>;
                  })}
                </ul> : <p className={styles.empty}>本次点评没有记录待补问点。</p>}
                {!!session.turns[0]?.feedback?.covered.length && <details>
                  <summary>首轮已讲清 · {session.turns[0].feedback.covered.length} 项</summary>
                  <ul>{session.turns[0].feedback.covered.map(line => <li key={line}>{line}</li>)}</ul>
                </details>}
              </> : <>
              <div className={styles.summaryGrid}>
                <section><h3>已讲清</h3>{session.summary.covered.length ? <ul>{session.summary.covered.map((line, index) => <li key={index}>{line}</li>)}</ul> : <p className={styles.empty}>本次没有记录到明确讲清的点。</p>}</section>
                <section><h3>仍需补齐</h3>{session.summary.remaining.length ? <SummaryIssues lines={session.summary.remaining} visibleCount={4} /> : <p className={styles.empty}>没有记录到新的缺口。</p>}</section>
              </div>
              {!!session.summary.inconsistent.length && <section><h3>需要修正的说法</h3><SummaryIssues lines={session.summary.inconsistent} visibleCount={3} /></section>}
              {!!session.summary.resolvedIssues?.length && <section><h3>本次已修正</h3><ul>
                {session.summary.resolvedIssues.map(issue => <li key={issue.issueId}><strong>{issue.text}</strong><blockquote>{issue.answerQuote}</blockquote></li>)}
              </ul></section>}
              </>}
            </div>
          </details>
          {summaryNextStep && <p className={styles.nextStep}><strong>下一步：</strong>{summaryNextStep}</p>}
          <div className={styles.actions}>
            {!knowledgeOutdated && <button type="button" className="btn" disabled={!busyIdle} onClick={() => void restartPractice()}>{busy === "restart" ? "正在创建新练习…" : "再练一次"}</button>}
            <Link className="btn-secondary" href={reportHref}>回到报告这项要求</Link>
            <Link className="btn-quiet" href="/reports">查看我的报告</Link>
          </div>
        </section>}
      </div>

      <PracticeSources key={turn?.turnIndex ?? "before-question"} turn={turn} session={session} />
    </div>
  </div>;
}

function PracticeSources({ turn, session, compact = false, basisId }: {
  turn: PracticeTurn | null; session: InterviewSession; compact?: boolean; basisId?: string;
}) {
  const sources = practiceTurnSources(turn, session);
  const { kind } = sources;
  const citations = basisId ? sources.citations.filter(item => item.citationId === basisId) : sources.citations;
  const knowledge = basisId ? sources.knowledge.filter(item => item.knowledgeId === basisId) : sources.knowledge;
  const title = kind === "session" ? "练习资料" : kind === "feedback" ? "本轮点评依据" : kind === "first-related" ? "首问关联依据" : "本轮题目依据";
  const content = <>
    {kind === "first-related" && <p className={styles.empty}>本轮沿用首问保存的依据。</p>}
    {citations.length ? <ul className={styles.evidenceList}>
      {citations.map((item, index) => {
        const material = session.materials.find(entry => entry.id === item.projectVersionId);
        const segments = item.filePath.split(/[/\\]/);
        const filename = segments.at(-1) || item.filePath;
        const path = segments[0] === item.projectVersionId ? segments.slice(1).join("/") : item.filePath;
        return <li className={styles.evidenceItem} key={item.citationId || `${item.filePath}:${item.lineStart}:${index}`}>
          <details open={!compact && kind !== "session" && index === 0}>
            <summary>
              <strong>{filename} · 第 {item.lineStart}{item.lineEnd === item.lineStart ? "" : `–${item.lineEnd}`} 行</strong>
              <span>{material && <>{displayMaterialTitle(material.title, material.id)} · 第 {material.versionNumber} 版 · </>}{item.provenance === "reference" ? "第三方参考，不计评级" : item.provenance === "portfolio" ? "本人材料" : "报告材料"}</span>
            </summary>
            {item.snippet ? <div className={styles.sourceSnippet}><EvidenceSnippet evidence={item} materials={session.materials} showContextNote={false} theme="dark"/></div>
              : <p className={styles.empty}>没有保存源码片段。</p>}
            {filename !== path && <p className={styles.sourcePath}>{path}</p>}
          </details>
        </li>;
      })}
    </ul> : !compact && <p className={styles.empty}>{kind === "feedback" ? "本轮点评没有保存材料引用。" : "没有保存对应的材料引用。"}</p>}
    {!!knowledge.length && <section className={styles.basisGroup}>
      <h3>技术知识</h3>
      <ul className={styles.knowledgeList}>
        {knowledge.map(item => <li key={item.knowledgeId}>
          <strong>{item.title}</strong>
          <span>{item.sourceLabel} · {item.sourceVersion} · {item.section}</span>
          <details><summary>出处详情</summary><span>{item.document}{item.sourceLocator ? ` · ${item.sourceLocator}` : ""}</span></details>
        </li>)}
      </ul>
    </section>}
    {!compact && session.materials.length > 0 && <details className={styles.savedDetails}>
      <summary>练习使用的固定版本</summary>
      <ul className={styles.materials}>
        {session.materials.map(material => <li key={`${material.kind}:${material.id}`}>{displayMaterialTitle(material.title, material.id)} · 第 {material.versionNumber} 版</li>)}
      </ul>
    </details>}
  </>;
  if (compact && turn) {
    const label = `第 ${turn.turnIndex + 1} 轮点评依据`;
    return citations.length || knowledge.length ? <details className={styles.inlineBasis}>
      <summary>{label}</summary>
      {content}
    </details> : <p className={styles.empty}>第 {turn.turnIndex + 1} 轮点评未保存依据。</p>;
  }
  return <aside className={styles.basis} aria-label={title}><h2>{title}</h2>{content}</aside>;
}
