// 传智杯48：证据等级名称与分数尺度纯格式模块单测（先红后实现）。
// 等级名须与后端 app/tools/evidence_levels.py 的 {1:基础线索, 2:局部操作, 3:任务实现} 一致；
// 未知历史等级保留原数字，不得伪造 /3、/5 之类的比例；65 只是当前规则上限。
import { test } from "node:test";
import assert from "node:assert/strict";
import { RULE_SCORE_CAP, RULE_SCORE_CAP_NOTE, evidenceLevelName } from "../src/lib/evidence-display.ts";

test("已知等级 1/2/3 显示为等级名称", () => {
  assert.equal(evidenceLevelName(1), "基础线索");
  assert.equal(evidenceLevelName(2), "局部操作");
  assert.equal(evidenceLevelName(3), "任务实现");
});

test("未知历史等级保留原数字，不伪造比例", () => {
  assert.equal(evidenceLevelName(4), "等级 4");
  assert.equal(evidenceLevelName(80), "等级 80");
  assert.equal(evidenceLevelName(100), "等级 100");
  for (const level of [4, 80, 100]) assert.ok(!evidenceLevelName(level).includes("/"));
});

test("65 只是当前规则上限，不引入 100 分口径", () => {
  assert.equal(RULE_SCORE_CAP, 65);
  assert.ok(RULE_SCORE_CAP_NOTE.includes("65"));
  assert.ok(RULE_SCORE_CAP_NOTE.includes("材料支持度"));
  assert.ok(!RULE_SCORE_CAP_NOTE.includes("100"));
  // “满分”只能以否定澄清（不是能力满分）出现，不得单独宣称
  assert.ok(!RULE_SCORE_CAP_NOTE.includes("满分") || RULE_SCORE_CAP_NOTE.includes("不是能力满分"));
});
