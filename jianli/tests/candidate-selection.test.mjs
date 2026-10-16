import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { HEATMAP_DEMO, DEMO_REQUIREMENTS, DEMO_LABELS, demoCellClass } from "../src/lib/heatmap-demo.ts";
import { filterApplications } from "../src/lib/application-comparison.ts";
const require=createRequire(import.meta.url);
const {transform}=require("sucrase");
function fixture(){
 const state=[];let cursor=0;
 const modules={react:{useState(v){const i=cursor++;if(!(i in state))state[i]=v;return[state[i],v=>state[i]=v];}},"react/jsx-runtime":require("react/jsx-runtime"),"@/lib/application-comparison":{filterApplications},"@/lib/heatmap-demo":{HEATMAP_DEMO,DEMO_REQUIREMENTS,DEMO_LABELS,demoCellClass},"./SkillRadar":{default:()=>null,__esModule:true}};
 const code=transform(readFileSync(new URL("../src/components/HeatmapDemo.tsx",import.meta.url),"utf8"),{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code;
 const mod={exports:{}};new Function("require","module","exports",code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
 const render=()=>{cursor=0;return mod.exports.default();};
 const nodes=n=>!n||typeof n!=="object"?[]:[n,...[n.props?.children].flat(Infinity).flatMap(nodes)];
 const buttons=tree=>nodes(tree).filter(n=>n.type==="button"&&n.props.className==="candidate-select");
 return {render,nodes,buttons};
}
test("name and evidence-cell selection move a unique visible candidate marker together",()=>{
 const f=fixture();let t=f.render();
 assert.deepEqual(f.buttons(t).map(b=>b.props["aria-pressed"]),[true,false,false]);
 f.buttons(t)[1].props.onClick();t=f.render();
 assert.deepEqual(f.buttons(t).map(b=>b.props["aria-pressed"]),[false,true,false]);
 assert.equal(f.nodes(t).filter(n=>n.type==="span"&&n.props.children==="当前候选人").length,1);
 assert.equal(f.nodes(t).filter(n=>n.type==="tr"&&n.props.className?.includes("bg-indigo-50/70")).length,1);
 const cell=f.nodes(t).find(n=>n.type==="button"&&n.props["aria-label"]?.startsWith(HEATMAP_DEMO[2].candidateName));
 const oldClass=cell.props.className;cell.props.onClick();t=f.render();
 assert.deepEqual(f.buttons(t).map(b=>b.props["aria-pressed"]),[false,false,true]);
 assert.equal(f.nodes(t).find(n=>n.props?.["aria-label"]===cell.props["aria-label"]).props.className,oldClass,"selection must not recolor evidence state");
});
test("filtered fallback highlights the candidate actually displayed and empty results have no stale marker",()=>{
 const f=fixture();let t=f.render();
 f.nodes(t).find(n=>n.type==="input").props.onChange({target:{value:"候选人 C"}});t=f.render();
 assert.equal(f.buttons(t).length,1);assert.equal(f.buttons(t)[0].props["aria-pressed"],true);
 f.nodes(t).find(n=>n.type==="input").props.onChange({target:{value:"nothing-matches"}});t=f.render();
 assert.equal(f.buttons(t).length,0);
 assert.equal(f.nodes(t).filter(n=>n.type==="span"&&n.props.children==="当前候选人").length,0);
});
