import test from "node:test";
import assert from "node:assert/strict";
import { buildSkillPanorama, panoramaStatus, createSkillPanoramaSession, PANORAMA_PAGE_SIZE } from "../src/lib/skill-panorama.ts";

const item = (requirementId, skill, verdict = "supported") => ({ requirementId, skill, verdict, requirementTitle: `Original ${requirementId}`, skillPath: ["not a grouping source"] });
const report = (id, items = [], overrides = {}) => ({ id, candidateId: "owner", jobId: `job-${id}`, jobTitle: `Job ${id}`, createdAt: "2026-11-01T10:00:00Z", materials: [{ kind: "project", id: "fixed-version", title: "Project", versionNumber: 1, contentHash: "hash-1" }], items, ...overrides });
const page = (items, total = items.length, n = 1) => ({ items, total, page: n, pageSize: PANORAMA_PAGE_SIZE });
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
function harness(overrides = {}) {
  let state; const calls = [];
  const api = { listReports: async n => { calls.push(["list", n]); return page([report("a")]); }, getReport: async id => { calls.push(["detail", id]); return report(id); }, errorMessage: e => e.message, ...overrides };
  const session = createSkillPanoramaSession("owner", api, value => { state = value; }); session.activate();
  return { session, calls, get state() { return state; } };
}

test("explicit skill names group only by case and whitespace; no fuzzy alias or skillPath merging", () => {
  const result = buildSkillPanorama([report("a", [item("1", " Python "), item("2", "python"), item("3", "Python  3"), item("4", "Py"), item("5", "", "partial")])]);
  assert.deepEqual(result.skills.map(s => s.name), ["Python", "Python 3", "Py"]);
  assert.equal(result.skills[0].contexts.length, 2); assert.equal(result.skills[0].category, "编程语言");
  assert.equal(result.skills[1].category, "其他 / 未分类"); assert.equal(result.unclassified.length, 1);
  assert.equal(result.contextCount, 5);
});
test("same requirement across reports/jobs retains distinct verdicts, fixed material versions and server latest flags", () => {
  const a = report("a", [item("same", "Python", "partial")], { isLatestForJob: false });
  const b = report("b", [item("same", "python", "supported")], { materials: [{ ...a.materials[0], id: "version-2", versionNumber: 2, contentHash: "hash-2" }] });
  const { skills } = buildSkillPanorama([a, b, a]);
  assert.equal(skills.length, 1); const s = skills[0]; assert.equal(s.contexts.length, 2);
  assert.equal(new Set(s.contexts.map(c => c.key)).size, 2);
  assert.deepEqual(s.contexts.map(c => c.item.verdict), ["partial", "supported"]);
  assert.deepEqual(s.contexts.map(c => c.materials[0].versionNumber), [1, 2]);
  assert.deepEqual(s.contexts.map(c => c.isLatestForJob), [false, undefined]);
  assert.equal(s.counts.partial, 1); assert.equal(s.counts.supported, 1);
});
test("all evidence states are counted; unsupported and unknown are not proficiency zero", () => {
  const verdicts = ["supported", "partial", "claimed_only", "gap", "unsupported", "new_server_status", "not_evaluated", "verified"];
  const result = buildSkillPanorama([report("a", verdicts.map((v, i) => item(String(i), "Python", v)))]);
  assert.deepEqual(result.counts, { supported: 2, partial: 1, claimed_only: 1, gap: 1, unsupported: 1, unknown: 2 });
  assert.equal(panoramaStatus(""), "unknown"); assert.equal(result.contextCount, verdicts.length);
});
test("first scope is one page, details concurrency is bounded, load more is explicit, repeated clicks do not duplicate", async () => {
  const reports = Array.from({ length: 14 }, (_, i) => report(String(i)));
  let running = 0, max = 0; const pages = [], details = [];
  const h = harness({ listReports: async (n, size) => { pages.push([n, size]); return page(reports.slice((n - 1) * size, n * size), 14, n); }, getReport: async id => {
    running++; max = Math.max(max, running); details.push(id); await new Promise(r => setTimeout(r, 2)); running--; return reports.find(r => r.id === id);
  } });
  await Promise.all([h.session.loadMore(), h.session.loadMore()]);
  assert.deepEqual(pages, [[1, 12]]); assert.equal(details.length, 12); assert.equal(max, 3);
  assert.equal(h.state.reports.length, 12); assert.equal(h.state.hasMore, true); assert.equal(h.state.total - h.state.summaries.length, 2);
  await h.session.loadMore(); assert.deepEqual(pages, [[1, 12], [2, 12]]); assert.equal(h.state.reports.length, 14); assert.equal(h.state.hasMore, false);
  await h.session.loadMore(); assert.equal(pages.length, 2);
});
test("partial detail failure keeps healthy records; retry only failed details, no older latest substitution", async () => {
  let fail = true; const reads = [];
  const old = report("old", [item("x", "Python")], { jobId: "job", isLatestForJob: false });
  const latest = report("latest", [item("x", "Python", "partial")], { jobId: "job", isLatestForJob: true });
  const h = harness({ listReports: async () => page([latest, old]), getReport: async id => { reads.push(id); if (fail && id === "latest") throw new Error("detail offline"); return id === "old" ? old : latest; } });
  await h.session.loadMore(); assert.equal(h.state.reports[0], old); assert.deepEqual(h.state.failures, { latest: "detail offline" });
  assert.equal(buildSkillPanorama(h.state.reports).skills[0].contexts[0].isLatestForJob, false);
  fail = false; await h.session.retryFailed(); assert.deepEqual(reads, ["latest", "old", "latest"]);
  assert.equal(h.state.reports.length, 2); assert.deepEqual(h.state.failures, {});
});
test("list page failure is retryable on same page and does not clear healthy content", async () => {
  let fail = true; const pages = [];
  const h = harness({ listReports: async n => { pages.push(n); if (n === 2 && fail) throw new Error("list offline"); return page([report(n === 1 ? "a" : "b")], 13, n); } });
  await h.session.loadMore(); await h.session.loadMore();
  assert.equal(h.state.reports.length, 1); assert.equal(h.state.listError, "list offline");
  fail = false; await h.session.loadMore(); assert.deepEqual(pages, [1, 2, 2]); assert.equal(h.state.reports.length, 2);
});
test("disposing while list pending never starts details or publishes stale data", async () => {
  const wait = deferred(); const h = harness({ listReports: () => wait.promise });
  const loading = h.session.loadMore(); const state = h.state; h.session.dispose(); wait.resolve(page([report("a")])); await loading;
  assert.equal(h.state, state); assert.deepEqual(h.calls, []);
});
test("disposing during details stops queued reads and ignores late result", async () => {
  const waits = Array.from({ length: 3 }, deferred), reads = [];
  const h = harness({ listReports: async () => page(Array.from({ length: 8 }, (_, i) => report(String(i)))), getReport: id => { reads.push(id); return waits[Number(id)].promise; } });
  const loading = h.session.loadMore(); await Promise.resolve(); assert.equal(reads.length, 3);
  h.session.dispose(); waits.forEach((w, i) => w.resolve(report(String(i)))); await loading;
  assert.equal(reads.length, 3); assert.equal(h.state.reports.length, 0);
});
test("strict effect cleanup/reactivation clears busy and rejects the previous generation", async () => {
  const waits = [deferred(), deferred()]; let calls = 0;
  const h = harness({ listReports: () => waits[calls++].promise });
  const first = h.session.loadMore(); h.session.dispose(); h.session.activate(); const second = h.session.loadMore();
  waits[1].resolve(page([report("new")])); await second; waits[0].resolve(page([report("stale")])); await first;
  assert.equal(h.state.busy, false); assert.deepEqual(h.state.reports.map(r => r.id), ["new"]);
});
test("foreign summary blocks before any detail; foreign detail or mismatched report ID clears all", async () => {
  const summary = harness({ listReports: async () => page([report("a", [], { candidateId: "other" })]) }); await summary.session.loadMore();
  assert.equal(summary.state.blocked, true); assert.deepEqual(summary.calls, []); assert.equal(summary.state.summaries.length, 0);
  for (const overrides of [{ candidateId: "other" }, { id: "other-report" }, { jobId: "other-job" }]) {
    const h = harness({ getReport: async id => report(id, [], overrides) }); await h.session.loadMore();
    assert.equal(h.state.blocked, true); assert.equal(h.state.reports.length, 0); assert.equal(h.state.summaries.length, 0);
  }
});
test("401 clears healthy content and in-flight generation; other detail errors remain local", async () => {
  let expire = false;
  const h = harness({ listReports: async n => page([report(n === 1 ? "a" : "b")], 13, n), getReport: async id => { if (expire) throw Object.assign(new Error("expired"), { status: 401 }); return report(id); } });
  await h.session.loadMore(); expire = true; await h.session.loadMore();
  assert.equal(h.state.reports.length, 0); assert.equal(h.state.summaries.length, 0); assert.equal(h.state.blocked, true);
});
test("empty account does not request detail or render artificial categories", async () => {
  const h = harness({ listReports: async () => page([]) }); await h.session.loadMore();
  assert.equal(h.state.total, 0); assert.equal(h.state.hasMore, false); assert.equal(h.state.busy, false); assert.deepEqual(h.calls, []);
  assert.deepEqual(buildSkillPanorama([]).skills, []);
});
