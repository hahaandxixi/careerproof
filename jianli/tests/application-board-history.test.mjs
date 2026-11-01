import test from "node:test";
import assert from "node:assert/strict";
import { applicationBoardHistoryState, readApplicationBoardHistory } from "../src/lib/application-board-history.ts";

const navigation = { page: 2, filters: { q: "Python", status: "viewed", requirementId: "fastapi", verdict: "supported" }, comparisonIds: ["a", "b", "u"] };

test("history retains only navigation fields and preserves Next router state", () => {
  const previous = { __NA: true, __PRIVATE_NEXTJS_INTERNALS_TREE: ["saved-route"] };
  const state = applicationBoardHistoryState(previous, "employer-a", "job-a", {
    ...navigation, report: { summary: "private report" }, replyText: "private draft", source: "private code", candidateName: "private name",
  });
  assert.deepEqual(readApplicationBoardHistory(state, "employer-a", "job-a"), navigation);
  assert.deepEqual(state.__PRIVATE_NEXTJS_INTERNALS_TREE, previous.__PRIVATE_NEXTJS_INTERNALS_TREE);
  assert.equal(state.__NA, true);
  for (const privateText of ["private report", "private draft", "private code", "private name"]) assert.ok(!JSON.stringify(state).includes(privateText));
  assert.notEqual(state, previous);
});

test("another account, another job and an unsigned identity cannot restore IDs or filters", () => {
  const state = applicationBoardHistoryState(null, "employer-a", "job-a", navigation);
  for (const [owner, job] of [["employer-b", "job-a"], ["employer-a", "job-b"], ["", "job-a"]]) {
    assert.deepEqual(readApplicationBoardHistory(state, owner, job), { page: 1, filters: { q: "", status: "", requirementId: "", verdict: "" }, comparisonIds: [] });
  }
});

test("malformed navigation cannot submit unsupported filters or an unbounded shortlist", () => {
  const state = applicationBoardHistoryState(null, "employer-a", "job-a", {
    page: Infinity, filters: { q: "x".repeat(300), status: "admin", requirementId: null, verdict: "verified" },
    comparisonIds: ["a", "a", null, 123, "", "b", "c", "d", "e"],
  });
  const saved = readApplicationBoardHistory(state, "employer-a", "job-a");
  assert.equal(saved.page, 1);
  assert.deepEqual(saved.filters, { q: "x".repeat(200), status: "", requirementId: "", verdict: "" });
  assert.deepEqual(saved.comparisonIds, ["a", "b", "c", "d"]);
});

test("server-clamped page and pruned authorized IDs replace the old history bookmark", () => {
  const previous = applicationBoardHistoryState(null, "employer-a", "job-a", navigation);
  const updated = applicationBoardHistoryState(previous, "employer-a", "job-a", { ...navigation, page: 1, comparisonIds: ["b", "u"] });
  assert.equal(readApplicationBoardHistory(updated, "employer-a", "job-a").page, 1);
  assert.deepEqual(readApplicationBoardHistory(updated, "employer-a", "job-a").comparisonIds, ["b", "u"]);
  assert.equal(readApplicationBoardHistory(previous, "employer-a", "job-a").page, 2);
});
