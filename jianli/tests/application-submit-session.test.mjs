// 传智杯44：投递提交管线回归。忙碌防重（单飞）、失败提示可见且可重试、成功提示替换旧提示。
import test from "node:test";
import assert from "node:assert/strict";
import { createApplicationSubmitSession } from "../src/lib/application-submit-session.ts";

function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function setup(overrides = {}) {
  const snapshots = [];
  const session = createApplicationSubmitSession(
    { submit: async () => ({}), errorMessage: e => e.message, ...overrides },
    state => snapshots.push(state),
  );
  return { session, state: () => snapshots.at(-1) };
}

test("提交成功：先进入忙碌，结束后 busy 归零并给出成功提示", async () => {
  const gate = deferred();
  const h = setup({ submit: () => gate.promise });
  const running = h.session.submit();
  assert.deepEqual(h.state(), { busy: true, notice: "", done: false }, "请求未返回前必须处于忙碌态");
  gate.resolve({});
  await running;
  assert.equal(h.state().busy, false);
  assert.equal(h.state().done, true);
  assert.match(h.state().notice, /已投递/);
});

test("忙碌防重：进行中的提交期间重复触发只发一次请求", async () => {
  let calls = 0;
  const gate = deferred();
  const h = setup({ submit: () => { calls += 1; return gate.promise; } });
  const first = h.session.submit();
  const second = h.session.submit();
  const third = h.session.submit();
  gate.resolve({});
  await first; await second; await third;
  assert.equal(calls, 1, "单飞期间重复点击不得发出第二次请求");
  assert.equal(h.state().done, true);
});

test("失败可重试：失败提示原样可见，busy 归零后再次提交发出新请求并成功", async () => {
  let calls = 0;
  const h = setup({ submit: () => { calls += 1; if (calls === 1) throw new Error("网络中断"); return {}; } });
  await h.session.submit();
  assert.equal(h.state().done, false);
  assert.match(h.state().notice, /网络中断/, "失败原因必须展示给用户");
  assert.equal(h.state().busy, false, "失败后按钮必须恢复可用才能重试");
  await h.session.submit();
  assert.equal(calls, 2, "重试必须真实发出第二次请求");
  assert.equal(h.state().done, true);
  assert.ok(!h.state().notice.includes("网络中断"), "重试成功后不得残留失败提示");
});

test("重试仍失败：提示替换为最新一次失败原因，不残留成功提示", async () => {
  let calls = 0;
  const h = setup({ submit: () => { calls += 1; return calls < 2 ? Promise.resolve({}) : Promise.reject(new Error("第二次失败")); } });
  await h.session.submit();
  assert.equal(h.state().done, true);
  await h.session.submit();
  assert.equal(h.state().done, false);
  assert.match(h.state().notice, /第二次失败/);
  assert.equal(h.state().busy, false);
});
