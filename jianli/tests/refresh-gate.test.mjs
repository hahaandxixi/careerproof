import test from "node:test";
import assert from "node:assert/strict";
import { createRefreshGate } from "../src/lib/refresh-gate.ts";

// B-06：visibilitychange、focus、pageshow 紧邻触发时必须合并为一次刷新，
// 已加载列表和已打开报告不得被重复收起；真实数据变化仍能触发后续刷新。
function setup(clock) {
  const runs = [];
  const gate = createRefreshGate(() => runs.push(clock.now), { windowMs: 3000, now: () => clock.now });
  return { gate, runs };
}

test("visibilitychange, focus and pageshow arriving together refresh once", () => {
  const clock = { now: 1000 };
  const { gate, runs } = setup(clock);
  assert.equal(gate.trigger(), true);
  assert.equal(gate.trigger(), false);
  assert.equal(gate.trigger(), false);
  assert.equal(runs.length, 1);
  assert.equal(runs[0], 1000);
});

test("a trigger after the merge window refreshes again with fresh time", () => {
  const clock = { now: 1000 };
  const { gate, runs } = setup(clock);
  gate.trigger();
  clock.now += 2999;
  assert.equal(gate.trigger(), false);
  assert.equal(runs.length, 1);
  clock.now += 1;
  assert.equal(gate.trigger(), true);
  assert.equal(runs.length, 2);
  assert.equal(runs[1], 4000);
});

test("hiding resets the merge window so the return always reloads", () => {
  const clock = { now: 1000 };
  const { gate, runs } = setup(clock);
  gate.trigger();
  clock.now += 500;
  gate.reset();
  assert.equal(gate.trigger(), true);
  assert.equal(runs.length, 2);
  assert.equal(runs[1], 1500);
});

test("each gate starts empty so a mount refresh is never absorbed", () => {
  const clock = { now: 0 };
  const { gate, runs } = setup(clock);
  assert.equal(gate.trigger(), true);
  assert.equal(runs.length, 1);
});
