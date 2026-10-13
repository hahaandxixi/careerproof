import { test } from "node:test";
import assert from "node:assert/strict";
import { radarScore, radarPointKind, radarSegments, radarSelection } from "../src/lib/skill-radar.ts";
const d = (id, verdict, score) => ({ requirementId:id, title:id, skill:id, verdict, score, weight:1 });
test("missing material never creates a point; unavailable and invalid scores are not invented zeros", () => {
  assert.equal(radarPointKind(d("gap","gap",0)),"none");
  assert.equal(radarPointKind(d("claim","claimed_only",20)),"claimed");
  assert.equal(radarPointKind(d("real-zero","supported",0)),"backed");
  for (const score of [null,undefined,NaN,Infinity,-1,101,"75"]) assert.equal(radarScore(d("bad","supported",score)),null);
  assert.equal(radarScore(d("na","unsupported",75)),null);
  assert.equal(radarScore(d("future","future",75)),null);
});
test("segments stop at gaps, self claims and unavailable axes instead of filling a misleading area", () => {
  // 传智杯48：正常数据改为 evidence-v3 单项可达值 65/40/15/10
  const dims=[d("a","supported",65),d("b","partial",40),d("c","gap",0),d("d","claimed_only",10)];
  assert.deepEqual(radarSegments(dims),[[0,1]]);
  assert.deepEqual(radarSegments(dims.slice(0,2)),[]);
});
test("selection joins only by requirement identity and never carries a missing citation from another requirement", () => {
  const dims=[d("first","supported",65),d("second","gap",0)];
  const items=[{requirementId:"first",evidenceList:[{citationId:"A-E1"}]}];
  assert.equal(radarSelection(dims,"second",items).item,undefined);
  assert.equal(radarSelection(dims,"first",items).item,items[0]);
  assert.equal(radarSelection(dims,"old-id",items).dimension,dims[0]);
  assert.equal(radarSelection([],"old-id",items).item,undefined);
  const newItems=[{requirementId:"first",evidenceList:[{citationId:"B-E1"}]}];
  assert.equal(radarSelection(dims,"first",newItems).item,newItems[0]);
});
