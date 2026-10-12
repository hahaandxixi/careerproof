// 传智杯44：投递展示口径回归。状态/回复/下一动作文案集中且不以查看下载推断录用。
import test from "node:test";
import assert from "node:assert/strict";
import {
  APPLICATION_STATUS_TEXT,
  applicationStatusText,
  applicationReplyText,
  applicationNextAction,
  applicationEventsSummary,
} from "../src/lib/application-display.ts";

test("五种投递状态都有确定的状态文案", () => {
  assert.deepEqual(Object.keys(APPLICATION_STATUS_TEXT).sort(), ["downloaded", "replied", "submitted", "viewed", "withdrawn"]);
  for (const status of Object.keys(APPLICATION_STATUS_TEXT)) assert.ok(applicationStatusText(status).length > 0);
});

test("未知状态原样显示，下一步只建议刷新，不臆造进展", () => {
  assert.equal(applicationStatusText("mystery"), "mystery");
  assert.equal(applicationNextAction("mystery"), "刷新投递状态获取最新进展。");
});

test("企业回复类型保留三类映射", () => {
  assert.equal(applicationReplyText("interview"), "面试邀请");
  assert.equal(applicationReplyText("continue"), "继续沟通");
  assert.equal(applicationReplyText("declined"), "暂不推进");
});

test("查看/下载状态的下一步必须等待回复并明示不代表通过筛选，不得推断录用", () => {
  for (const status of ["viewed", "downloaded"]) {
    const next = applicationNextAction(status);
    assert.match(next, /等待企业回复/);
    assert.match(next, /不代表通过筛选/);
    assert.doesNotMatch(next, /录用概率|有望通过|即将进入面试|已录用/);
  }
});

test("每种已知状态都有非空的下一步动作", () => {
  for (const status of Object.keys(APPLICATION_STATUS_TEXT)) assert.ok(applicationNextAction(status).length > 0);
});

test("事件列表摘要只给条数，不展开事件内容", () => {
  assert.equal(applicationEventsSummary([{}, {}, {}]), "投递记录（3 条）");
  assert.equal(applicationEventsSummary([]), "投递记录（0 条）");
});
