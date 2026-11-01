import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveSupportScale, supportMeasure, DEMO_SUPPORT_SCALE, formatSupportNumber } from "../src/lib/support-index.js";
const axis = (score, formulaVersion="evidence-v4", verdict="supported") => ({score,formulaVersion,verdict});

test("confirmed rules map raw/cap to the same unrounded geometry; no raw mutation",()=>{
 const axes=[65,40,10,0].map(v=>axis(v)); const before=JSON.stringify(axes), scale=resolveSupportScale(axes);
 assert.equal(scale.mode,"index");
 for(const [i,text] of ["100","61.5","15.4","0"].entries()) {
   const m=supportMeasure(axes[i],scale);assert.equal(m.text,text);assert.equal(m.ratio,axes[i].score/65);
   assert.equal(m.value,axes[i].score/65*100);assert.ok(!m.text.includes("%"));
 }
 assert.equal(JSON.stringify(axes),before);assert.equal(formatSupportNumber(100),"100");
});
test("whole chart resolves known mixed versions with shared cap, never from selected or maximum",()=>{
 const axes=[axis(10,"evidence-v3"),axis(40,"evidence-v4")];
 assert.equal(resolveSupportScale(axes).denominator,65);
 assert.equal(resolveSupportScale([axis(10)]).denominator,65);
 for(const version of ["evidence-v2","v3","synthetic-only","synthetic-ui",null,"future"]){
   const scale=resolveSupportScale([axes[0],axis(65,version)]);assert.equal(scale.mode,"raw");
   assert.equal(supportMeasure(axes[0],scale).ratio,10/100);assert.match(scale.label,/未换算/);
 }
 assert.equal(resolveSupportScale([]).mode,"raw");
 assert.match(supportMeasure(axis(40,"unknown"),resolveSupportScale(axes)).issue,/不一致/);
});
test("public sample metadata is explicit; saved synthetic-tagged reports are not inferred",()=>{
 const axes=[axis(65,"synthetic-only")];
 assert.equal(resolveSupportScale(axes).mode,"raw");
 assert.equal(supportMeasure(axes[0],resolveSupportScale(axes,DEMO_SUPPORT_SCALE)).text,"100");
 assert.equal(resolveSupportScale([axis(65,"synthetic-ui")],DEMO_SUPPORT_SCALE).mode,"raw");
});
test("gap, unsupported, missing values, claims and a genuinely scored zero remain distinct",()=>{
 const scale=resolveSupportScale([axis(65)]);
 for(const verdict of ["gap","unsupported","future"])assert.equal(supportMeasure(axis(0,"evidence-v4",verdict),scale).ratio,null);
 assert.equal(supportMeasure(axis(0),scale).ratio,0);
 assert.equal(supportMeasure(axis(10,"evidence-v4","claimed_only"),scale).text,"15.4");
 for(const score of [null,undefined,NaN,Infinity,-1,66,100,"65"]){const m=supportMeasure(axis(score),scale);assert.equal(m.ratio,null);assert.equal(m.value,null);assert.ok(m.issue);assert.equal(m.raw,score);}
 const legacy=resolveSupportScale([axis(65,"unknown")]);
 assert.equal(supportMeasure(axis(101,"unknown"),legacy).ratio,null);
 assert.match(supportMeasure(axis(66),legacy).issue,/超过已确认/);
});
