import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { careerPlanConfigurationBlocked, careerPlanFailureMessage } from "../src/lib/career-plan-display.ts";
const require = createRequire(import.meta.url);
const { transform } = require("sucrase");
const jsx = require("react/jsx-runtime");

// Execute the real component with deterministic hooks and synthetic APIs.
// This tests state transitions, not browser rendering or a real model request.
function fixture({ failMaterials = false, generationResult = null } = {}) {
  const cells = [], effects = [], dependencies = [];
  let cursor = 0, effectCursor = 0, createCalls = 0, listCalls = 0, historyCalls = 0;
  const same = (a,b) => a && a.length === b.length && a.every((v,i) => Object.is(v,b[i]));
  const hooks = {
    useState(initial) { const i = cursor++; if (!(i in cells)) cells[i] = initial; return [cells[i], value => {cells[i] = typeof value === "function" ? value(cells[i]) : value;}]; },
    useEffect(callback, deps) {const i=effectCursor++;if(!same(dependencies[i],deps)){dependencies[i]=deps;effects.push(callback);}},
  };
  const api = {
    async listResumes(){listCalls++;if(failMaterials)throw Error("synthetic list unavailable");return [{versions:[{id:"resume-v2",status:"completed"}]}];},
    async listProjects(){return [{versions:[{id:"project-v3",status:"completed"}]}];},
    async createCareerPlan(){createCalls++;if(generationResult)return generationResult;throw Error("synthetic generation unavailable");},
    async latestCareerPlan(){historyCalls++;throw Error("synthetic history unavailable");},
  };
  const picker = name => Object.assign(()=>null,{testName:name});
  const ResumePicker=picker("resume"),ProjectPicker=picker("project"),ErrorNotice=picker("error");
  const modules = {
    "react": hooks, "react/jsx-runtime":jsx,"next/link":{default:picker("link"),__esModule:true},
    "@/lib/api/client":{api,errorMessage:e=>e.message},
    "@/lib/api/domain":{CATEGORY_LABELS:{},EMPLOYMENT_LABELS:{}},
    "@/lib/recommendation-selection":{jobAnalysisHref:()=>"/jobs/job1",resolveInitialMaterialSelection:()=>({resumeVersionId:"",projectVersionIds:[]})},
    "@/lib/career-plan-display":{careerPlanRecommendations:()=>[],visibleCareerChanges:()=>[],careerPlanConfigurationBlocked,careerPlanFailureMessage},
    "./AccessGate":{ErrorNotice},"./AuthProvider":{useAuth:()=>({user:{id:"student-1"}})},
    "./ProjectVersionPicker":{default:ProjectPicker,__esModule:true},"./ResumeVersionPicker":{default:ResumePicker,__esModule:true},
    "@/lib/verdict-display.js":{verdictLabel:v=>v},
  };
  const code=transform(readFileSync(new URL("../src/components/CareerRecommendations.tsx",import.meta.url),"utf8"),{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code;
  const mod={exports:{}};new Function("require","module","exports",code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
  const render=()=>{cursor=effectCursor=0;return mod.exports.default({});};
  const settle=async()=>{while(effects.length)effects.shift()();for(let i=0;i<8;i++)await Promise.resolve();};
  const nodes=(node)=>{if(!node||typeof node!=="object")return [];return [node,...[node.props?.children].flat(Infinity).flatMap(nodes)];};
  const get=(tree,type)=>{const n=nodes(tree).find(n=>n.type===type);assert.ok(n, String(type.testName||type));return n;};
  return {render,settle,get,ResumePicker,ProjectPicker,ErrorNotice,nodes,calls:()=>({createCalls,listCalls,historyCalls})};
}

test("failed generation retry retains chosen versions and consent without automatically calling AI",async()=>{
 const f=fixture();let tree=f.render();await f.settle();tree=f.render();
 f.get(tree,f.ResumePicker).props.onChange("resume-v2");tree=f.render();
 f.get(tree,f.ProjectPicker).props.onChange(["project-v3"]);tree=f.render();
 f.get(tree,"input").props.onChange({target:{checked:true}});tree=f.render();
 await f.get(tree,"form").props.onSubmit({preventDefault(){}});tree=f.render();
 const notice=f.get(tree,f.ErrorNotice);assert.ok(notice.props.message.includes("unavailable"));notice.props.retry();tree=f.render();await f.settle();tree=f.render();
 assert.equal(f.get(tree,f.ResumePicker).props.selectedId,"resume-v2");
 assert.deepEqual(f.get(tree,f.ProjectPicker).props.selectedIds,["project-v3"]);
 assert.equal(f.get(tree,"input").props.checked,true);
 assert.deepEqual(f.calls(),{createCalls:1,listCalls:1,historyCalls:0});
});

test("material list failure retry really rereads the list",async()=>{
 const f=fixture({failMaterials:true});let tree=f.render();await f.settle();tree=f.render();
 f.get(tree,f.ErrorNotice).props.retry();tree=f.render();await f.settle();tree=f.render();
 assert.equal(f.calls().listCalls,2);assert.equal(f.calls().createCalls,0);
});

test("history retry is a read and does not reload material selection or create a plan",async()=>{
 const f=fixture();let tree=f.render();await f.settle();tree=f.render();
 f.get(tree,f.ResumePicker).props.onChange("resume-v2");tree=f.render();
 const history=f.nodes(tree).find(n=>n.type==="button"&&n.props.children==="查看上次保存的规划");assert.ok(history);
 await history.props.onClick();tree=f.render();
 await f.get(tree,f.ErrorNotice).props.retry();await f.settle();tree=f.render();
 assert.equal(f.get(tree,f.ResumePicker).props.selectedId,"resume-v2");
 assert.deepEqual(f.calls(),{createCalls:0,listCalls:1,historyCalls:2});
});

test("a disabled AI result blocks repeated generation even after material selection changes",async()=>{
 const f=fixture({generationResult:{aiPlan:null,aiStatus:"external_ai_disabled",aiFallbackUsed:true,planId:null,materials:[],recommendations:[],changes:[],summary:"合成规则候选"}});
 let tree=f.render();await f.settle();tree=f.render();
 f.get(tree,f.ResumePicker).props.onChange("resume-v2");tree=f.render();
 f.get(tree,"input").props.onChange({target:{checked:true}});tree=f.render();
 await f.get(tree,"form").props.onSubmit({preventDefault(){}});tree=f.render();
 const button=f.nodes(tree).find(n=>n.type==="button"&&n.props.children==="当前 AI 配置不可用");
 assert.ok(button?.props.disabled);
 assert.ok(f.nodes(tree).some(n=>n.type==="p"&&n.props.children===careerPlanFailureMessage("external_ai_disabled")));
 f.get(tree,f.ResumePicker).props.onChange("resume-v3");tree=f.render();
 await f.get(tree,"form").props.onSubmit({preventDefault(){}});
 assert.equal(f.calls().createCalls,1,"changing material does not repair environment configuration");
});
