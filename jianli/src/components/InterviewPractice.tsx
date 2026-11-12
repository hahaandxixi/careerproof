"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, errorMessage } from "@/lib/api/client";
import type { InterviewSession, PracticeTurn } from "@/lib/api/domain";
import { displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import {
  canSubmit, consentItems, draftKey, newClientToken, openTurn, practiceStatusLabel,
  canRetryFeedback, feedbackStatusLabel, generationPending, questionRetryNote, savedSubmission, summaryLine, tokenKey, turnLabel, turnNotice,
} from "@/lib/interview-practice";
import { useAuth } from "./AuthProvider";
import { ErrorNotice } from "./AccessGate";
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
  const busyIdle = busy === null;
  const knowledgeOutdated = Boolean(session.knowledgeOutdated);

  return <div className={styles.page}>
    {loadError && <ErrorNotice message={loadError} retry={() => void load()} />}
    <header className={styles.head}>
      <nav className={styles.crumb} aria-label="练习位置">
        <Link href="/reports">我的报告</Link><span aria-hidden="true">/</span>
        <Link href={reportHref}>{jobTitle || "岗位报告"}</Link><span aria-hidden="true">/</span>
        <span>模拟面试</span>
      </nav>
      <div className={styles.titleRow}>
        <h1 className={styles.title}>模拟面试</h1>
        <span className={styles.status}>{practiceStatusLabel(session.status)}</span>
      </div>
      <div className={styles.requirement}>
        <span>本项岗位要求</span>
        <strong>{session.requirementTitle || session.skill}</strong>
      </div>
      <div className={styles.meta}>
        <span>技能 <b>{session.skill || "未标注"}</b></span>
        {session.materials.map(material => (
          <span key={`${material.kind}:${material.id}`}>{displayMaterialTitle(material.title, material.id)} <b>v{material.versionNumber}</b></span>
        ))}
        <span>材料与知识依据在创建练习时固定</span>
      </div>
    </header>

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

        {session.turns.length > 1 && <nav className={styles.turnTrack} aria-label="练习轮次">
          {session.turns.map(turn => <a key={turn.turnIndex} href={`#practice-turn-${turn.turnIndex}`} aria-current={turn === session.turns.at(-1) ? "step" : undefined}>
            <strong>第 {turn.turnIndex + 1} 轮</strong><span>{feedbackStatusLabel(turn)}</span>
          </a>)}
        </nav>}
        {session.turns.map(turn => {
          const isBusy = busy === turn.turnIndex;
          const evidence = turn.feedback?.citations ?? [];
          const previous = !!turn.feedback && turn !== session.turns.at(-1);
          const content = <article className={styles.turn} data-state={turn.state} aria-label={turnLabel(turn)}>
            <div className={styles.turnHead}>
              <span className={styles.turnLabel}>{turnLabel(turn)}<b>{turn.kind === "follow_up" ? "根据上一轮回答追问" : `围绕 ${session.skill || "本项要求"}`}</b></span>
              <span className={styles.turnState}>{turn.state === "question" ? "待回答" : "回答已保存"}<span aria-hidden="true"> · </span>{feedbackStatusLabel(turn)}</span>
            </div>
            <p className={styles.question}>{turn.question}</p>
            {!!turn.focus && <p className={styles.focus}>关注点：{turn.focus}</p>}
            {!!turn.citations.length && <div className={styles.basisNote} aria-label="首问关联材料">
              <strong>首问关联材料：</strong>
              {turn.citations.map(item => <span key={item.citationId || `${item.filePath}:${item.lineStart}`}>{item.filePath.split("/").pop()} · 第 {item.lineStart}–{item.lineEnd} 行</span>)}
            </div>}

            {turn.state === "question" && <div>
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

            {turn.state !== "question" && !!turn.answerText && <div className={styles.answerSaved} aria-label="已保存的回答">{turn.answerText}</div>}

            {turn.state !== "question" && !turn.feedback && <div className={styles.actions}>
              <span className={styles.notice} data-tone={turn.state === "failed" ? "failed" : "info"}>{feedbackReadTurn === turn.turnIndex ? "暂时无法确认点评重试结果，请读取保存状态。" : turnNotice(turn)}</span>
              {feedbackReadTurn !== turn.turnIndex && canRetryFeedback(turn) && <button type="button" className="btn-secondary" disabled={!busyIdle || knowledgeOutdated} onClick={() => void retry(turn)}>{isBusy ? "正在重试…" : "重试点评"}</button>}
              <button type="button" className="btn-quiet" disabled={!busyIdle} onClick={() => void load()}>读取保存状态</button>
            </div>}

            {turn.feedback && <section className={styles.feedback} aria-label="本轮点评">
              <p className={styles.feedbackCounts}><span>讲清 {turn.feedback.covered.length}</span><span>需修正 {turn.feedback.inconsistent.length}</span><span>待补充 {turn.feedback.missing.length}</span></p>
              {!!turn.feedback.covered.length && <div className={styles.feedbackBlock} data-kind="covered"><h4>讲清的内容</h4><ul>{turn.feedback.covered.map((line, index) => <li key={index}>{line}</li>)}</ul></div>}
              {!!turn.feedback.inconsistent.length && <div className={styles.feedbackBlock} data-kind="inconsistent">
                <h4>与材料或原理不一致</h4>
                <ul>{turn.feedback.conflictDetails?.length ? turn.feedback.conflictDetails.map((conflict, index) => {
                  const file = evidence.find(item => item.citationId === conflict.basisId);
                  const principle = turn.feedback?.knowledge.find(item => item.knowledgeId === conflict.basisId);
                  return <li key={index}>
                    <q>{conflict.answerQuote}</q> {conflict.reason}
                    {file && <p>{file.filePath.split("/").pop()} · 第 {file.lineStart}–{file.lineEnd} 行</p>}
                    {principle && <p>{principle.title}</p>}
                  </li>;
                }) : turn.feedback.inconsistent.map((line, index) => <li key={index}>{line}</li>)}</ul>
              </div>}
              {!!turn.feedback.missing.length && <div className={styles.feedbackBlock} data-kind="missing"><h4>遗漏的关键点</h4><ul>{turn.feedback.missing.map((line, index) => <li key={index}>{line}</li>)}</ul></div>}
              {!!turn.feedback.reviewSuggestion && <div className={styles.suggestion}><strong>复习建议：</strong>{turn.feedback.reviewSuggestion}</div>}
              {!!evidence.length && <div className={styles.citations}>
                <h4>点评依据的材料片段</h4>
                <ul className={styles.citationList}>
                  {evidence.map(item => <li key={item.citationId || `${item.filePath}:${item.lineStart}`}>
                    <strong>{item.filePath.split("/").pop()} · 第 {item.lineStart}–{item.lineEnd} 行</strong>
                    <span>{item.filePath}{item.provenance === "reference" ? " · 第三方参考，不计评级" : ""}</span>
                    <pre className={styles.snippet} tabIndex={0} aria-label={`原文 ${item.filePath} 第 ${item.lineStart} 至 ${item.lineEnd} 行`}><code>{item.snippet}</code></pre>
                  </li>)}
                </ul>
              </div>}
              {!!turn.feedback.knowledge.length && <div className={styles.citations}>
                <h4>点评依据的技术知识</h4>
                <ul className={styles.knowledgeList}>
                  {turn.feedback.knowledge.map(item => <li key={item.knowledgeId}>
                    <strong>{item.title}</strong>
                    <span>{item.sourceLabel} · {item.sourceVersion} · {item.section}</span>
                  </li>)}
                </ul>
              </div>}
              {!evidence.length && <p className={styles.hint}>本轮点评没有保存材料引用。</p>}
              <Link className={styles.reportLink} href={reportHref}>核对原报告这项要求 →</Link>
            </section>}
          </article>;
          const anchor = `practice-turn-${turn.turnIndex}`;
          return previous ? <details key={turn.turnIndex} id={anchor} className={styles.previousTurn}>
            <summary><strong>第 {turn.turnIndex + 1} 轮 · 已点评</strong><span>讲清 {turn.feedback!.covered.length} · 需修正 {turn.feedback!.inconsistent.length} · 待补充 {turn.feedback!.missing.length}</span></summary>
            {content}
          </details> : <div key={turn.turnIndex} id={anchor} className={styles.turnAnchor}>{content}</div>;
        })}

        {session.summary && <section className={styles.summary} aria-label="练习小结">
          <h2>练习小结</h2>
          <p className={styles.summaryNote}>{summaryLine(session.summary)}</p>
          <div className={styles.summaryGrid}>
            <section><h3>已讲清</h3>{session.summary.covered.length ? <ul>{session.summary.covered.map((line, index) => <li key={index}>{line}</li>)}</ul> : <p className={styles.empty}>本次没有记录到明确讲清的点。</p>}</section>
            <section><h3>仍需补齐</h3>{session.summary.remaining.length ? <SummaryIssues lines={session.summary.remaining} visibleCount={4} /> : <p className={styles.empty}>没有记录到新的缺口。</p>}</section>
          </div>
          {!!session.summary.inconsistent.length && <section><h3>需要修正的说法</h3><SummaryIssues lines={session.summary.inconsistent} visibleCount={3} /></section>}
          {!!session.summary.resolvedIssues?.length && <section><h3>本次已修正</h3><ul>
            {session.summary.resolvedIssues.map(issue => <li key={issue.issueId}><strong>{issue.text}</strong><blockquote>{issue.answerQuote}</blockquote></li>)}
          </ul></section>}
          {!!session.summary.nextStep && <p className={styles.suggestion}><strong>下一步：</strong>{session.summary.nextStep}</p>}
          <p className={styles.summaryNote}>{session.summary.note}</p>
          <div className={styles.actions}>
            {!knowledgeOutdated && <button type="button" className="btn" disabled={!busyIdle} onClick={() => void restartPractice()}>{busy === "restart" ? "正在创建新练习…" : "再练一次"}</button>}
            <Link className="btn-secondary" href={reportHref}>回到报告这项要求</Link>
            <Link className="btn-quiet" href="/reports">查看我的报告</Link>
          </div>
        </section>}
      </div>

      <aside className={styles.basis} aria-label="练习依据">
        <div className={styles.basisHead}>
          <h2>练习依据</h2>
          <p>来自这份报告的固定材料版本与技术知识；作答前只展示标题与出处，不展示参考要点。</p>
        </div>
        <div className={styles.basisGroup}>
          <h3>材料引用 · {session.evidence.length} 处</h3>
          {session.evidence.length ? <ul className={styles.evidenceList}>
            {session.evidence.map(item => <li className={styles.evidenceItem} key={item.citationId || `${item.filePath}:${item.lineStart}`}>
              <details>
                <summary>{item.filePath.split("/").pop()} · 第 {item.lineStart}–{item.lineEnd} 行<span>{item.provenance === "reference" ? "第三方参考" : "本人材料"} · {item.filePath}</span></summary>
                <pre className={styles.snippet} tabIndex={0} aria-label={`原文 ${item.filePath} 第 ${item.lineStart} 至 ${item.lineEnd} 行`}><code>{item.snippet}</code></pre>
              </details>
            </li>)}
          </ul> : <p className={styles.empty}>这项要求没有已保存的代码引用。练习会依据岗位原文与技术知识出场景题，不会编造项目实现。</p>}
        </div>
        <div className={styles.basisGroup}>
          <h3>技术知识 · {session.knowledge.length} 条</h3>
          {session.knowledge.length ? <ul className={styles.knowledgeList}>
            {session.knowledge.map(item => <li key={item.knowledgeId}>
              <strong>{item.title}</strong>
              <span>{item.sourceLabel} · {item.sourceVersion}</span>
              <span>{item.document} · {item.section}{item.sourceLocator ? ` · ${item.sourceLocator}` : ""}</span>
              <span className={styles.reviewTag}>{item.reviewStatus === "reviewed" ? `已对照官方文档整理 · ${item.reviewedAt}` : "待复核"}</span>
            </li>)}
          </ul> : <p className={styles.empty}>暂无可用的技术知识条目；练习只依据这份报告的材料出题。</p>}
        </div>
        <div className={styles.basisGroup}>
          <h3>回答范围</h3>
          <p className={styles.empty}>练习独立保存，不写入成长任务草稿，也不改写报告判断、技能状态或企业已收到的投递快照。</p>
          <Link className={styles.reportLink} href={reportHref}>回到原报告定位这项要求 →</Link>
        </div>
      </aside>
    </div>
  </div>;
}


