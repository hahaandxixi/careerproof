import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { comparisonRows, comparisonCounts, filterComparisonRows, groupComparisonSources, sourceRecordKind } from "../src/lib/report-comparison-display.ts";
import * as logic from "../src/lib/report-comparison-display.ts";
import * as sourceLabels from "../src/lib/source-label.ts";
import * as levels from "../src/lib/evidence-display.ts";

function source(overrides = {}) {
  return { citationId: "R1-E1", sourceId: "source-1", projectVersionId: "version-1", projectFileId: "file-1", filePath: "version-1/src/service.py", lineStart: 10, lineEnd: 20, snippet: "def register():\n    return save()", contentHash: "hash", provenance: "portfolio", contextComplete: true, contextNote: "", evidenceType: "implementation", ...overrides };
}
function fixture({ added = [], removed = [], changes = [], oldVerdict = "supported", verdict = oldVerdict, sources = [source()], oldSources = [source()] } = {}) {
  const item = { requirementId: "req", title: "实现报名接口", status: "existing", baseRequirement: {weight: 3}, targetRequirement: {weight: 3}, baseLevel: 2, targetLevel: 2, baseAiStatus: "validated", targetAiStatus: "validated", baseReview: "pending", targetReview: "pending", baseExplanation: "同一解释", targetExplanation: "同一解释", addedEvidence: added, removedEvidence: removed, changes };
  const report = (id, verdict, evidenceList) => ({id, createdAt:"2026-10-29T00:00:00Z", materials:[{id:"version-1", kind:"project", title:"报名服务", versionNumber:1,contentHash:"hash"}], items:[{requirementId:"req", verdict, evidenceList, confirmationStatus:"pending"}]});
  const base = report("base-report", oldVerdict, oldSources), current = report("current-report", verdict, sources);
  return { value: {baseId:base.id,targetId:current.id,contextChanges:[],baseMaterials:base.materials,targetMaterials:current.materials,limitations:["引用减少不代表文件删除"],items:[item]}, base, current };
}
const rows = f => comparisonRows(f.value, f.base, f.current);

test("identical saved states produce zero changes and keep unchanged records accessible", () => {
  const f=fixture(), result=rows(f);
  assert.deepEqual(comparisonCounts(result), {changed:0,all:1,evidence:0,status:0,needs:0,unchanged:1});
  assert.equal(filterComparisonRows(result,"changed").length,0);
  assert.equal(filterComparisonRows(result,"unchanged").length,1);
  assert.match(result[0].summary,/没有检测到变化/);
  assert.equal(result[0].retained.length,1);
});

test("added evidence and unchanged judgment are counted independently", () => {
  const extra=source({citationId:"R1-E2",projectFileId:"test-file",filePath:"version-1/tests/test_registration.py"});
  const f=fixture({added:[extra],changes:["evidence"],sources:[source(),extra]});
  const result=rows(f), c=comparisonCounts(result);
  assert.equal(c.evidence,1); assert.equal(c.status,0);
  assert.equal(result[0].retained.length,1);
  assert.match(result[0].summary,/判断状态未改变/);
  assert.equal(sourceRecordKind(extra),"测试代码引用");
  assert.equal(sourceRecordKind(source({filePath:"pytest-output.txt"})),"记录文件引用（需核对原文）");
});

test("status transitions and remaining gaps come from the two actual reports", () => {
  const f=fixture({oldVerdict:"claimed_only",verdict:"supported",added:[source()],changes:["evidence","level"]});
  const r=rows(f)[0]; assert.equal(r.baseStatus,"仅简历声明"); assert.equal(r.targetStatus,"有证据支持");
  assert.equal(comparisonCounts([r]).status,1); assert.equal(comparisonCounts([r]).needs,0);
  for (const verdict of ["partial","claimed_only","gap"]) assert.equal(comparisonCounts(rows(fixture({verdict}))).needs,1);
  assert.equal(comparisonCounts(rows(fixture({verdict:"unsupported"}))).needs,0,"rule not covered is not an invented missing-material judgment");
});

test("source dedup retains aliases and separates versions, paths, ranges and contents", () => {
  const s=source(), alias=source({citationId:"R1-E9",sourceId:"alias-source"});
  const groups=groupComparisonSources([s,alias,source({projectVersionId:"version-2"}),source({lineEnd:21}),source({snippet:"different code"}),source({filePath:"other/service.py"})]);
  assert.equal(groups.length,5); assert.deepEqual(groups[0].citationIds,["R1-E1","R1-E9"]);
  assert.deepEqual(groups[0].sourceIds,["source-1","alias-source"]);
  assert.equal(groups[0].source.snippet,s.snippet);
});

test("different report identities are rejected rather than mixing snapshots", () => {
  const f=fixture(); assert.throws(()=>comparisonRows(f.value,{...f.base,id:"other"},f.current),/身份不一致/);
});

const require=createRequire(import.meta.url), React=require("react");
const {renderToStaticMarkup}=require("react-dom/server"), {transform}=require("sucrase");
function load(path, modules) {
  const mod={exports:{}};
  const code=transform(readFileSync(new URL(path,import.meta.url),"utf8"),{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code;
  new Function("require","module","exports",code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
  return mod.exports.default;
}
function render(f, filter="changed") {
  const runtime=require("react/jsx-runtime");
  const Explanation=load("../src/components/ReportItemExplanation.tsx",{"react/jsx-runtime":runtime});
  const View=load("../src/components/ReportComparisonView.tsx",{
    react:{useState:()=>[filter,()=>{}]},"react/jsx-runtime":runtime,
    "next/link":{__esModule:true,default:props=>React.createElement("a",props)},
    "@/lib/report-comparison-display":logic,"@/lib/source-label":sourceLabels,"@/lib/evidence-display":levels,
    "@/lib/growth-workflow":{GROWTH_CHANGES:{}},"./ReportItemExplanation":{__esModule:true,default:Explanation},
  });
  return renderToStaticMarkup(React.createElement(View,f));
}

test("real comparison view folds all source groups and keeps removed citations on the base report", () => {
  const evidence=Array.from({length:25},(_,i)=>source({citationId:`R1-E${i+1}`,lineStart:i+1,lineEnd:i+1,snippet:`original ${i}`}));
  const f=fixture({added:[evidence[0]],removed:evidence.slice(1),changes:["evidence"],sources:[evidence[0]]});
  const html=render(f);
  assert.doesNotMatch(html,/<details[^>]*\sopen(?:[\s=>])/);
  assert.match(html,/新增引用 · 1 处/); assert.match(html,/移除展示的引用 · 24 处/);
  assert.match(html,/href="\/reports\/base-report#citation-R1-E2"/);
  assert.match(html,/href="\/reports\/current-report#citation-R1-E1"/);
  assert.match(html,/original 24/); assert.match(html,/version-1\/src\/service.py/);
  assert.match(html,/min-w-0/); assert.match(html,/max-w-full overflow-auto/);
  assert.match(html,/grid-cols-1/);
});

test("no-change message, filters, counts and old explanations remain available without text rewriting", () => {
  const f=fixture(), original=structuredClone(f);
  assert.match(render(f),/本次没有检测到变化/);
  const html=render(f,"all"); assert.match(html,/没有变化 1/);
  assert.match(html,/同一解释/);
  assert.doesNotMatch(html,/<details[^>]*\sopen(?:[\s=>])/);
  assert.deepEqual(f,original);
});

test("panel only displays complete authorized report data and preserves actual read failures", async () => {
  for (const fail of [false,true]) {
    const f=fixture(), cells=[], refs=[]; let cursor=0, ri=0;
    const reads=[]; const View=()=>null;
    const Panel=load("../src/components/ReportComparisonPanel.tsx",{
      react:{useEffect(){},useRef(initial){return refs[ri++]??={current:initial};},useState(initial){const i=cursor++;if(!(i in cells))cells[i]=initial;return[cells[i],v=>{cells[i]=v;}];}},
      "react/jsx-runtime":require("react/jsx-runtime"),"./ReportComparisonView":{__esModule:true,default:View},
      "@/lib/api/client":{errorMessage:e=>e.message,api:{previousComparison:async()=>f.value,getReport:async id=>{reads.push(id);if(fail&&id===f.base.id)throw new Error("原报告暂时无法读取");return id===f.base.id?f.base:f.current;}}},
    });
    const renderPanel=()=>{cursor=0;ri=0;return Panel({reportId:f.current.id,revision:""});};
    function find(node,p){if(!node||typeof node!=="object")return null;if(Array.isArray(node))return node.map(n=>find(n,p)).find(Boolean);return p(node)?node:find(node.props?.children,p);}
    await find(renderPanel(),n=>n.type==="button").props.onClick();
    const tree=renderPanel();assert.deepEqual(reads,[f.base.id,f.current.id]);
    if(fail){assert.equal(find(tree,n=>n.type===View),undefined);assert.equal(find(tree,n=>n.props?.role==="alert").props.children,"原报告暂时无法读取");}
    else {const view=find(tree,n=>n.type===View);assert.equal(view.props.base,f.base);assert.equal(view.props.current,f.current);}
  }
});
