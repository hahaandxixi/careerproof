import * as navigation from "../src/lib/report-navigation.ts";
import * as demoPresentation from "../src/lib/demo-display-identity.js";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { comparisonRows, comparisonCounts, filterComparisonRows, groupComparisonSources, sourceRecordKind } from "../src/lib/report-comparison-display.ts";
import * as logic from "../src/lib/report-comparison-display.ts";
import * as sourceLabels from "../src/lib/source-label.ts";
import * as levels from "../src/lib/evidence-display.ts";
import * as pairs from "../src/lib/report-pair.ts";

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
  assert.match(result[0].summary,/引用集合未变（保留 1 处），判断状态未变/);
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
    "@/lib/demo-display-identity.js":demoPresentation,
    react:{useState:()=>[filter,()=>{}]},"react/jsx-runtime":runtime,
    "next/link":{__esModule:true,default:props=>React.createElement("a",props)},
    "@/lib/report-navigation":navigation,"@/lib/report-comparison-display":logic,"@/lib/source-label":sourceLabels,"@/lib/evidence-display":levels,
    "@/lib/report-display":{aiStatusLabel:(value)=>value ? String(value) : "未记录"},
    "@/lib/growth-workflow":{GROWTH_CHANGES:{}},"./ReportItemExplanation":{__esModule:true,default:Explanation},
  });
  return renderToStaticMarkup(React.createElement(View,f));
}

test("real comparison view opens changed sources and keeps removed citations on the base report", () => {
  const evidence=Array.from({length:25},(_,i)=>source({citationId:`R1-E${i+1}`,lineStart:i+1,lineEnd:i+1,snippet:`original ${i}`}));
  const f=fixture({added:[evidence[0]],removed:evidence.slice(1),changes:["evidence"],sources:[evidence[0]]});
  const html=render(f);
  assert.equal((html.match(/<details[^>]*\sopen(?:[\s=>])/g)??[]).length,1);
  assert.match(html,/新增引用 · 1 处/); assert.match(html,/移除展示的引用 · 24 处/);
  assert.match(html,/href="\/reports\/base-report#citation-R1-E2"/);
  assert.match(html,/href="\/reports\/current-report#citation-R1-E1"/);
  assert.match(html,/original 24/); assert.match(html,/version-1\/src\/service.py/);
  assert.match(html,/min-w-0/); assert.match(html,/max-w-full overflow-auto/);
});

test("no-change message, filters, counts and old explanations remain available without text rewriting", () => {
  const f=fixture(), original=structuredClone(f);
  assert.match(render(f),/本次没有检测到变化/);
  const html=render(f,"all"); assert.match(html,/没有变化<span[^>]*>1<\/span>/);
  assert.match(html,/同一解释/);
  assert.doesNotMatch(html,/<details[^>]*\sopen(?:[\s=>])/);
  assert.deepEqual(f,original);
});

test("panel only displays complete authorized report data and preserves actual read failures", async () => {
  for (const fail of [false,true]) {
    const f=fixture(), cells=[]; let cursor=0, effect, started=false, session, comparisons=0;
    for (const report of [f.base,f.current]) Object.assign(report,{jobId:"job",candidateId:"owner",analysisMode:"rules"});
    const reads=[]; const View=()=>null;
    const Panel=load("../src/components/ReportComparisonPanel.tsx",{
      react:{useEffect(fn){if(!started){started=true;effect=fn;}},useMemo(fn){return session??=fn();},useState(initial){const i=cursor++;if(!(i in cells))cells[i]=initial;return[cells[i],v=>{cells[i]=v;}];}},
      "react/jsx-runtime":require("react/jsx-runtime"),"./ReportComparisonView":{__esModule:true,default:View},
      "@/lib/report-pair":pairs,
      "@/lib/demo-display-identity.js":demoPresentation,
      "@/lib/api/client":{errorMessage:e=>e.message,api:{listReports:async()=>({items:[f.base,f.current],page:1,pageSize:50,total:2}),compareReports:async(a,b)=>{comparisons++;assert.equal(a,f.base.id);assert.equal(b,f.current.id);return f.value;},getReport:async id=>{reads.push(id);if(fail&&id===f.base.id)throw new Error("原报告暂时无法读取");return id===f.base.id?f.base:f.current;}}},
    });
    const renderPanel=()=>{cursor=0;const outer=Panel({report:f.current,revision:""});return outer.type(outer.props);};
    function find(node,p){if(!node||typeof node!=="object")return null;if(Array.isArray(node))return node.map(n=>find(n,p)).find(Boolean);return p(node)?node:find(node.props?.children,p);}
    renderPanel();const dispose=effect();
    for(let i=0;i<8;i++)await Promise.resolve();
    const button=find(renderPanel(),n=>n.type==="button");assert.equal(button.props.disabled,false);button.props.onClick();
    for(let i=0;i<8;i++)await Promise.resolve();
    const tree=renderPanel();assert.deepEqual(reads,[f.base.id,f.current.id]);assert.equal(comparisons,1);
    if(fail){assert.equal(find(tree,n=>n.type===View),undefined);assert.equal(find(tree,n=>n.props?.role==="alert").props.children,"原报告暂时无法读取");}
    else {const view=find(tree,n=>n.type===View);assert.equal(view.props.base,f.base);assert.equal(view.props.current,f.current);}
    dispose();
  }
});

test("real rule-version key warns on comparison while preserving original rule identities", () => {
  for (const [formulaChanged, evidenceChanged] of [[true,false],[false,true],[true,true],[false,false]]) {
    const changed = formulaChanged || evidenceChanged;
    const f=fixture({changes:changed?["rule_version"]:[]});
    f.value.contextChanges=changed?["rule_version"]:[];
    Object.assign(f.base.items[0],{formulaVersion:"formula-A",evidenceLevelVersion:"evidence-A"});
    Object.assign(f.current.items[0],{formulaVersion:formulaChanged?"formula-B":"formula-A",evidenceLevelVersion:evidenceChanged?"evidence-B":"evidence-A"});
    const html=render(f,"all");
    assert.equal(html.includes("比较依据有变化"),changed);
    if (changed) {
      assert.match(html,/formula-A/);
      assert.match(html,/evidence-A/);
      assert.equal(html.includes("formula-B"),formulaChanged);
      assert.equal(html.includes("evidence-B"),evidenceChanged);
    }
  }
});
