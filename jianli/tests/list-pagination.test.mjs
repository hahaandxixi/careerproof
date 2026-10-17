import test from "node:test";
import assert from "node:assert/strict";
import { pageBounds, unpackList } from "../src/lib/list-pagination.js";
import { createApplicationListSession } from "../src/lib/application-list-session.ts";
import { createApplicationBoardSession } from "../src/lib/application-board-session.ts";
import { api } from "../src/lib/api/client.ts";

test("exactly twenty final rows disable next; page six reaches row 101", () => {
  assert.equal(pageBounds({ total: 40, page: 2, pageSize: 20 }).next, false);
  assert.deepEqual(pageBounds({ total: 101, page: 6, pageSize: 20 }), { pages: 6, previous: true, next: false, start: 101, end: 101 });
  assert.deepEqual(pageBounds({ total: 0, page: 1, pageSize: 20 }), { pages: 1, previous: false, next: false, start: 0, end: 0 });
});

test("notification target is visible without inflating page membership or totals", () => {
  const result = unpackList({ items: [{ id: "page-row" }, { id: "notification-target" }], total: 101, page: 6, pageSize: 20, pageItemCount: 1 });
  assert.equal(result.items.length, 2);
  assert.equal(result.pagination.pageItemCount, 1);
  assert.equal(result.pagination.total, 101);
});

test("late old page cannot overwrite new page, its metadata, or hidden state", async () => {
  let resolve;
  const old = new Promise(yes => { resolve = yes; });
  let calls = 0, state;
  const session = createApplicationListSession({
    list: () => ++calls === 1 ? old : Promise.resolve({ items: [{ id: "new" }], total: 101, page: 6, pageSize: 20 }),
    withdraw: async () => {}, errorMessage: e => e.message,
  }, next => { state = next; });
  session.activate();
  const pending = session.refresh(); await session.refresh();
  resolve({ items: [{ id: "stale" }], total: 100, page: 1, pageSize: 20 }); await pending;
  assert.equal(state.items[0].id, "new"); assert.equal(state.pagination.page, 6);
  session.clear(); assert.deepEqual(state.items, []); assert.equal(state.pagination, undefined);
});

test("candidate page change clears opened report and cannot deliver an out-of-page download", async () => {
  let page = 1, delivered = false, state;
  const session = createApplicationBoardSession({
    list: async () => ({ items: [{ id: page === 1 ? "a" : "b" }], total: 21, page, pageSize: 20 }),
    open: async id => ({ id, report: { summary: "private" } }),
    download: async () => { page = 2; return { blob: new Blob(["private"]), filename: "private.txt" }; },
    reply: async () => {}, errorMessage: e => e.message,
  }, next => { state = next; });
  session.activate(); await session.open("a"); assert.equal(state.selected.id, "a");
  assert.equal(await session.download(() => { delivered = true; }), false);
  assert.equal(delivered, false); assert.equal(state.selected, null); assert.equal(state.pagination.page, 2);
});

test("HTTP adapters pass canonical paging and filter job status before pagination", async () => {
  const original = globalThis.fetch, urls = [];
  globalThis.fetch = async url => {
    urls.push(new URL(url, "http://127.0.0.1"));
    return new Response(JSON.stringify({ code: 0, data: { items: [], total: 0, page: 1, pageSize: 20, unavailableCount: 0 }, message: "success" }), { headers: { "Content-Type": "application/json" } });
  };
  try {
    await api.myApplications(3, 20, "only-this-job"); await api.jobApplications("job", 6, 20);
    await api.listReports(2, 20); await api.listGrowthTasks(4, 20); await api.notifications(2, true, 50);
    assert.equal(urls[0].searchParams.get("jobId"), "only-this-job");
    assert.deepEqual(urls.map(url => url.searchParams.get("page")), ["3", "6", "2", "4", "2"]);
    assert.deepEqual(urls.map(url => url.searchParams.get("pageSize")), ["20", "20", "20", "20", "50"]);
    assert.equal(urls[4].searchParams.get("unread_only"), "true");
  } finally { globalThis.fetch = original; }
});
