import test from "node:test";
import assert from "node:assert/strict";
import { applicationAnchorId, includeApplicationTarget } from "../src/lib/notification-session.ts";
import { createApplicationAnchorRevealer } from "../src/lib/application-anchor.ts";

// 合成数据：仅格式合法的 UUID，不对应任何真实投递。
const TARGET = "0f0e0d0c-1b2a-4c3d-8e9f-0a1b2c3d4e5f";
const OTHER = "aa11bb22-cc33-4dd8-ee99-ff0011223344";

function harness({ hash = "", present = new Set() } = {}) {
  const state = { hash, present };
  const scrolls = [];
  const revealer = createApplicationAnchorRevealer({
    parseAnchorId: applicationAnchorId,
    readHash: () => state.hash,
    findTarget: id => (state.present.has(id)
      ? { scrollIntoView: options => scrolls.push({ id, options }) }
      : null),
  });
  return { state, scrolls, revealer };
}

test("B-15: one explicit anchor navigation scrolls exactly once; refreshes never re-scroll", () => {
  const { state, scrolls, revealer } = harness({ hash: `#application-${TARGET}` });
  // 加载中：items 为空、DOM 未渲染任何行 → 等待目标。
  assert.equal(revealer.attempt([], []), "waiting");
  // items 首次到达（includeApplicationTarget 已补入目标）且行已渲染 → 滚动一次。
  state.present.add(TARGET); state.present.add(OTHER);
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "revealed");
  assert.equal(scrolls.length, 1);
  assert.deepEqual(scrolls[0], { id: TARGET, options: { block: "center" } });
  // 可见性刷新：loading 清空后 items 重新发布 → 不再滚动（视口不被劫持）。
  assert.equal(revealer.attempt([], []), "idle");
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "idle");
  assert.equal(scrolls.length, 1);
  assert.ok(state.hash); // 残留锚点 hash 本身不应触发再次滚动
});

test("B-15: only a NEW anchor navigation may scroll again", () => {
  const { state, scrolls, revealer } = harness({ hash: `#application-${TARGET}`, present: new Set([TARGET]) });
  assert.equal(revealer.attempt([TARGET], [TARGET]), "revealed");
  assert.equal(scrolls.length, 1);
  // 用户点击另一条通知：hash 变为新锚点 → 再滚一次。
  state.hash = `#application-${OTHER}`;
  state.present.add(OTHER);
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "revealed");
  assert.equal(scrolls.length, 2);
  assert.equal(scrolls[1].id, OTHER);
  // 同 hash 的后续 items 变化不再滚动。
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "idle");
  // 锚点被清除（如 clearApplicationAnchor 的 replaceState）后不滚动。
  state.hash = "";
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "idle");
  assert.equal(scrolls.length, 2);
});

test("B-15: a target hidden by filters reports filtered-out instead of failing silently", () => {
  const { state, scrolls, revealer } = harness({ hash: `#application-${TARGET}` });
  // 目标在 items 中但被筛选条件排除（企业端 filterApplications 的 visible 不含它）。
  assert.equal(revealer.attempt([TARGET, OTHER], [OTHER]), "filtered-out");
  assert.equal(scrolls.length, 0);
  // 刷新后依旧被筛掉：保持提示，不滚动、不循环。
  assert.equal(revealer.attempt([TARGET, OTHER], [OTHER]), "filtered-out");
  assert.equal(scrolls.length, 0);
  // 用户按提示清除筛选：目标回到 visible 并渲染 → 恰好滚动一次，之后不再滚动。
  state.present.add(TARGET);
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "revealed");
  assert.equal(scrolls.length, 1);
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "idle");
});

test("B-15: dismissing the filtered-out notice consumes the pending anchor", () => {
  const { state, scrolls, revealer } = harness({ hash: `#application-${TARGET}` });
  assert.equal(revealer.attempt([TARGET], []), "filtered-out");
  revealer.dismiss();
  // 用户选择保留当前筛选：即使之后目标可见，也不再突然滚动。
  state.present.add(TARGET);
  assert.equal(revealer.attempt([TARGET], [TARGET]), "idle");
  assert.equal(scrolls.length, 0);
});

test("B-15: an unavailable target whose hash was cleared externally stops waiting", () => {
  const { state, scrolls, revealer } = harness({ hash: `#application-${TARGET}` });
  assert.equal(revealer.attempt([OTHER], [OTHER]), "waiting");
  // includeApplicationTarget 的 onUnavailable → clearApplicationAnchor（replaceState 不触发 hashchange）。
  state.hash = "";
  assert.equal(revealer.attempt([OTHER], [OTHER]), "idle");
  assert.equal(scrolls.length, 0);
});

test("B-15: non-application or missing hashes never scroll", () => {
  for (const hash of ["", "#requirement-abc", `#application-${TARGET}?evil=1`, "#application-not-a-uuid"]) {
    const { scrolls, revealer } = harness({ hash, present: new Set([TARGET, OTHER]) });
    assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "idle", hash);
    assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "idle", hash);
    assert.equal(scrolls.length, 0, hash);
  }
});

test("B-15: a stale rendered element cannot bypass the authorized list or active filter", () => {
  const { scrolls, revealer } = harness({ hash: `#application-${TARGET}`, present: new Set([TARGET]) });
  assert.equal(revealer.attempt([OTHER], [OTHER]), "waiting");
  assert.equal(revealer.attempt([TARGET, OTHER], [OTHER]), "filtered-out");
  assert.equal(scrolls.length, 0);
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "revealed");
  assert.deepEqual(scrolls, [{ id: TARGET, options: { block: "center" } }]);
});

test("B-15: re-navigating after a filtered-out notice re-evaluates the new target", () => {
  const { state, scrolls, revealer } = harness({ hash: `#application-${TARGET}`, present: new Set([OTHER]) });
  // 目标被企业筛选排除 → 报告 filtered-out（页面转为可操作提示）。
  assert.equal(revealer.attempt([TARGET, OTHER], [OTHER]), "filtered-out");
  assert.equal(scrolls.length, 0);
  // 提示未关闭时用户又导航到可见目标：新定位生效，恰好滚动新目标一次，旧提示对应的导航作废。
  state.hash = `#application-${OTHER}`;
  assert.equal(revealer.attempt([TARGET, OTHER], [OTHER]), "revealed");
  assert.deepEqual(scrolls.map(scroll => scroll.id), [OTHER]);
  assert.equal(revealer.attempt([TARGET, OTHER], [OTHER]), "idle");
  assert.equal(scrolls.length, 1);
  // 前进/后退回仍被筛掉的目标：提示重现而非静默；清除筛选（目标行渲染）后定位一次并收敛。
  state.hash = `#application-${TARGET}`;
  assert.equal(revealer.attempt([TARGET, OTHER], [OTHER]), "filtered-out");
  state.present.add(TARGET);
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "revealed");
  assert.equal(scrolls.length, 2);
  assert.equal(scrolls[1].id, TARGET);
  assert.equal(revealer.attempt([TARGET, OTHER], [TARGET, OTHER]), "idle");
});

test("B-15: closing a filtered-out notice still allows the next navigation to reveal", () => {
  const { state, scrolls, revealer } = harness({ hash: `#application-${TARGET}` });
  assert.equal(revealer.attempt([TARGET], []), "filtered-out");
  revealer.dismiss();
  // 关闭只消费当前导航：之后的新导航（hashchange）必须仍能定位。
  state.hash = `#application-${OTHER}`;
  state.present.add(OTHER);
  assert.equal(revealer.attempt([OTHER], [OTHER]), "revealed");
  assert.equal(scrolls.length, 1);
});

test("B-15: a withdrawn anchor target takes the notice path and never scrolls or opens", async () => {
  const state = { hash: `#application-${TARGET}`, present: new Set([OTHER]) };
  const scrolls = [];
  const revealer = createApplicationAnchorRevealer({
    parseAnchorId: applicationAnchorId,
    readHash: () => state.hash,
    findTarget: id => (state.present.has(id) ? { scrollIntoView: () => scrolls.push(id) } : null),
  });
  const current = [{ id: OTHER, jobId: "job" }];
  // 组件 list() 的真实流程：已撤回目标经 detail 读取得到 404 → onUnavailable（组件同时清除 hash 并给出不可访问提示）。
  let unavailable = 0;
  const items = await includeApplicationTarget(
    current, async () => { throw { status: 404 }; }, TARGET, "job",
    () => { unavailable++; state.hash = ""; },
  );
  assert.equal(unavailable, 1);
  assert.equal(items, current); // 撤回目标不得混入授权列表
  // hash 已清除 → 定位器不再等待，也不滚动；打开动作只存在于用户显式点击且必经后端鉴权。
  assert.equal(revealer.attempt([OTHER], [OTHER]), "idle");
  assert.equal(scrolls.length, 0);
  assert.equal(revealer.attempt([OTHER], [OTHER]), "idle");
  // 无权限（403）不得被吞掉：异常向上抛，由页面错误态拦截，同样不触发不可访问提示。
  await assert.rejects(
    includeApplicationTarget(current, async () => { throw { status: 403 }; }, TARGET, "job", () => { unavailable++; }),
    error => error.status === 403,
  );
  assert.equal(unavailable, 1);
});
