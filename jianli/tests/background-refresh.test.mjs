import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { transform } from "sucrase";
import { generationPending } from "../src/lib/interview-practice.ts";

const auth = readFileSync(new URL("../src/components/AuthProvider.tsx", import.meta.url), "utf8").replace(/\r\n/g, "\n");
const practice = readFileSync(new URL("../src/components/InterviewPractice.tsx", import.meta.url), "utf8").replace(/\r\n/g, "\n");

function section(source, start, end) {
  const left = source.indexOf(start);
  const right = source.indexOf(end, left + start.length);
  assert.ok(left >= 0 && right > left, "The tested component handler must exist");
  return source.slice(left, right);
}

function compile(source, context, result) {
  const code = transform(source, { transforms: ["typescript"] }).code;
  return Function(...Object.keys(context), code + "; return " + result)(...Object.values(context));
}

class ApiError extends Error {
  constructor(status) {
    super("Request failed");
    this.status = status;
  }
}

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
};

test("background auth error preserves the signed-in identity, while switch and confirmed logout replace it", async () => {
  const replies = [new Error("network"), { id: "B", role: "enterprise" }, new ApiError(401)];
  let user = { id: "A", role: "enterprise" }, status = "authenticated";
  const reload = compile(section(auth, "  const reload = useCallback", "  useEffect("), {
    operation: { current: 0 }, useCallback: fn => fn, ApiError, errorMessage: String,
    setUser: next => { user = next; }, setError: () => {},
    setStatus: next => { status = typeof next === "function" ? next(status) : next; },
    api: { getMe: async () => {
      const next = replies.shift();
      if (next instanceof Error) throw next;
      return next;
    } },
  }, "reload");

  await reload();
  assert.equal(user.id, "A");
  assert.equal(status, "authenticated");
  await reload();
  assert.equal(user.id, "B");
  assert.equal(status, "authenticated");
  await reload();
  assert.equal(user, null);
  assert.equal(status, "unauthenticated");
});

const load = section(practice, "  const load = useCallback", "  useEffect(");
const pendingHelper = section(practice, "function practicePending(", "export default function");
const pollEffect = section(practice, "  useEffect(() => {\n    if (!pending", "  const current = openTurn");
const snapshot = status => ({ questionTask: { status }, turns: [] });

for (const obsolete of ["success", "401", "transport"]) {
  test("overlapping manual read ignores stale " + obsolete + " and continues until terminal", async () => {
    const firstPoll = deferred(), manual = deferred();
    const terminal = snapshot("succeeded"), freshPending = snapshot("running");
    const responses = [firstPoll.promise, manual.promise, Promise.resolve(terminal)];
    const timers = new Map();
    let timerId = 0, effect, session, progress, error;
    const context = {
      useEffect: fn => { effect = fn; }, useCallback: fn => fn,
      pending: true, busy: null, id: "fixture", active: { current: true },
      requestEpoch: { current: 0 }, generationPending, ApiError, errorMessage: String,
      setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
      clearTimeout: id => timers.delete(id),
      api: { getInterviewSession: () => responses.shift() },
      setSession: value => { session = value; },
      setProgressError: value => { progress = value; },
      setLoadError: value => { error = value; },
      setFeedbackReadTurn: () => {}, setLoading: () => {},
    };
    const reload = compile(pendingHelper + load + pollEffect, context, "load");
    const cleanup = effect();
    const takeTimer = () => {
      assert.equal(timers.size, 1);
      const [id, callback] = timers.entries().next().value;
      timers.delete(id);
      return callback();
    };
    const olderRead = takeTimer();
    const manualRead = reload();
    manual.resolve(freshPending);
    await manualRead;
    if (obsolete === "success") firstPoll.resolve(snapshot("pending"));
    else firstPoll.reject(obsolete === "401" ? new ApiError(401) : new Error("offline"));
    await olderRead;
    assert.equal(session, freshPending);
    assert.equal(progress, "");
    assert.equal(error, "");
    await takeTimer();
    assert.equal(session, terminal);
    assert.equal(timers.size, 0);
    cleanup();
  });
}

test("unmount prevents an in-flight poll from publishing or scheduling", async () => {
  const inFlight = deferred();
  let effect, timer, writes = 0, scheduled = 0;
  compile(pendingHelper + pollEffect, {
    useEffect: fn => { effect = fn; },
    pending: true, busy: null, id: "fixture", requestEpoch: { current: 0 },
    api: { getInterviewSession: () => inFlight.promise },
    generationPending, ApiError, errorMessage: String,
    setTimeout: fn => { timer = fn; return ++scheduled; }, clearTimeout: () => {},
    setSession: () => { writes++; }, setLoadError: () => {}, setProgressError: () => {},
  }, "null");
  const cleanup = effect();
  const read = timer();
  cleanup();
  inFlight.resolve(snapshot("running"));
  await read;
  assert.equal(writes, 0);
  assert.equal(scheduled, 1);
});

test("a pre-start GET cannot overwrite the session returned by starting practice", async () => {
  const older = deferred();
  const started = { turns: [{ turnIndex: 1 }] };
  let session;
  const handlers = compile(load + section(practice, "  const start = async", "  const submit = async"), {
    useCallback: fn => fn, requestEpoch: { current: 0 }, active: { current: true },
    id: "fixture", session: null, consent: true, ApiError, errorMessage: String,
    api: { getInterviewSession: () => older.promise, startInterviewSession: async () => started },
    setSession: value => { session = value; }, setLoading: () => {}, setLoadError: () => {},
    setProgressError: () => {}, setFeedbackReadTurn: () => {}, setBusy: () => {},
    setActionError: () => {}, setNotice: () => {},
  }, "({ load, start })");
  const initial = handlers.load();
  await handlers.start();
  older.resolve({ turns: [] });
  await initial;
  assert.equal(session, started);
});
