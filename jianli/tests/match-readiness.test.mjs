// 传智杯83：岗位详情"无已完成简历"时不再是灰按钮死路。
// 原问题：没有 completed 简历版本时按钮 disabled，且页面不给任何说明或上传入口。
import test from "node:test";
import assert from "node:assert/strict";

import { matchReadiness } from "../src/lib/match-readiness.ts";

test("loading 时不催上传，避免重复建材料", () => {
  const state = matchReadiness({ loading: true, completedResumeCount: 0 });
  assert.equal(state.kind, "loading");
});

test("零个已完成简历 → 明确说明缺什么并给出已有入口", () => {
  const state = matchReadiness({ loading: false, completedResumeCount: 0 });
  assert.equal(state.kind, "missing-resume");
  assert.equal(state.actionHref, "/portfolio");
  assert.match(state.actionLabel, /上传简历/);
  assert.match(state.message, /还没有解析完成的简历版本/);
  // 说明不能暗示已经投递或已分享材料。
  assert.doesNotMatch(state.message, /已投递|已分享/);
});

test("有已完成简历 → 正常出表单", () => {
  assert.equal(matchReadiness({ loading: false, completedResumeCount: 1 }).kind, "ready");
  assert.equal(matchReadiness({ loading: false, completedResumeCount: 3 }).kind, "ready");
});

test("解析中的版本不算可用：只有 completed 才计入", () => {
  // 调用方只把 status === "completed" 的版本计入数量，这里固定该契约。
  const parsingOnly = matchReadiness({ loading: false, completedResumeCount: 0 });
  assert.equal(parsingOnly.kind, "missing-resume");
});
