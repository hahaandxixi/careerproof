import test from "node:test";
import assert from "node:assert/strict";
import * as draft from "../src/lib/job-draft.ts";

const prose = "负责开发企业业务接口并编写测试，能够使用Python分析数据和维护服务。";
const quote = "能够使用Python分析数据和维护服务";
const row = (text, part = quote) => ({ rawText: part, skillName: "Python", weight: 3,
  isRequired: true, sourceQuote: part,
  sourceStart: Array.from(text.slice(0, text.indexOf(part))).length,
  sourceEnd: Array.from(text.slice(0, text.indexOf(part)) + part).length });

test("ordinary Chinese and valid historical code-point references remain valid", () => {
  assert.equal(draft.quoteStillMatches(prose, row(prose)), true);
  assert.equal(draft.quoteStillMatches(prose, {rawText:"manual"}), true);
});
test("a non-BMP character before or within a quote uses code points", () => {
  const before = "🚀" + prose;
  const inside = prose.replace("Python", "🚀Python");
  assert.equal(draft.quoteStillMatches(before, row(before)), true);
  assert.equal(draft.quoteStillMatches(inside, row(inside, quote.replace("Python", "🚀Python"))), true);
});
test("negative, fractional, inverted, missing and excessive offsets are rejected", () => {
  for (const [sourceStart,sourceEnd] of [[-1,3],[0.5,3],[3,1],[0,Infinity],[0,999],[null,3]]) {
    assert.equal(draft.quoteStillMatches("abc", {sourceQuote:"abc",sourceStart,sourceEnd}), false);
  }
});
test("source selection converts code-point boundaries to UTF-16", () => {
  assert.deepEqual(draft.sourceSelectionRange("🚀ab🧪cd",1,4), [2,6]);
  assert.deepEqual(draft.sourceSelectionRange("🚀ab🧪cd",0,1), [0,2]);
  assert.equal(draft.sourceSelectionRange("abc",0,4), null);
});
test("only a current unedited response supplies the canonical text", () => {
  const gate=draft.createDraftRequestGuard(), ticket=gate.start();
  const result={normalizedDescription:prose,requirements:[row(prose)]};
  assert.equal(draft.currentDraftSource(gate,ticket,result),prose);
  gate.sourceChanged();
  assert.equal(draft.currentDraftSource(gate,ticket,result),null);
  const stale=gate.start(); gate.start();
  assert.equal(draft.currentDraftSource(gate,stale,result),null);
});
test("legacy responses without a canonical basis fail visibly, not by guessing trim", () => {
  const gate=draft.createDraftRequestGuard(), ticket=gate.start();
  assert.throws(()=>draft.currentDraftSource(gate,ticket,{requirements:[row(prose)]}),/原文/);
  assert.throws(()=>draft.currentDraftSource(gate,ticket,{normalizedDescription:"  "+prose,requirements:[row(prose)]}),/原文/);
});
