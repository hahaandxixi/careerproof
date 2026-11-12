import * as demoPresentation from "../src/lib/demo-display-identity.js";
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
const require=createRequire(import.meta.url), React=require("react"), {renderToStaticMarkup}=require("react-dom/server"), {transform}=require("sucrase");
registerHooks({resolve(id,context,next){
 if(id.startsWith(".")&&!/\.[a-z]+$/i.test(id)) {try{return next(new URL(id+".ts",context.parentURL).href,context);}catch{}}
 return next(id,context);
},load(url,context,next){
 if(url.endsWith(".ts"))return{format:"module",shortCircuit:true,source:transform(readFileSync(fileURLToPath(url),"utf8"),{transforms:["typescript"]}).code};
 return next(url,context);
}});
const helpers=await import("../src/lib/report-follow-up.ts");
const taskNavigation=await import("../src/lib/task-navigation.ts");
const reportId="11111111-1111-1111-1111-111111111111", requirementId="22222222-2222-2222-2222-222222222222";
const query=()=>new URLSearchParams({sourceReport:reportId,sourceRequirement:requirementId});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};};
const nodes=tree=>!tree||typeof tree!=="object"?[]:[tree,...React.Children.toArray(tree.props?.children).flatMap(nodes)];

/** Controlled production hooks/handlers, not a real clipboard, browser navigation or API permission test. */
function fixture(filename, initialProps={}, environment={}) {
 const slots=[],effects=[],pending=[],cleanup=[],requests=[],calls=[];
 let index=0,props=initialProps,tree;
 const react={
  useState(initial){const i=index++;if(!(i in slots))slots[i]=initial;return[slots[i],value=>{slots[i]=typeof value==="function"?value(slots[i]):value;}];},
  useRef(initial){const i=index++;return slots[i]??={current:initial};},
  useEffect(fn,deps){const i=index++;if(!effects[i]||deps.some((v,j)=>!Object.is(v,effects[i][j])))pending.push(()=>{cleanup[i]?.();cleanup[i]=fn();});effects[i]=deps;},
 };
 const modules={"@/lib/demo-display-identity.js":demoPresentation,react,"react/jsx-runtime":require("react/jsx-runtime"),"next/link":{__esModule:true,default:props=>React.createElement("a",props)},
  "next/navigation":{useSearchParams:()=>environment.query??new URLSearchParams()},
  "@/lib/report-follow-up":helpers,"@/lib/api/client":{errorMessage:error=>error.message,api:{getReport(id){calls.push(id);const request=deferred();requests.push(request);return request.promise;},listResumes(){return environment.lists?environment.lists():Promise.resolve(environment.resumes??[])},listProjects(){return environment.lists?environment.lists():Promise.resolve(environment.projects??[])}}}};
 const code=transform(readFileSync(new URL(`../src/components/${filename}.tsx`,import.meta.url),"utf8"),{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code;
 const mod={exports:{}};new Function("require","module","exports",code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
 function commit(){index=0;tree=mod.exports.default(props);while(pending.length)pending.shift()();index=0;tree=mod.exports.default(props);}
 commit();
 return{requests,calls,commit,tree:()=>tree,html(){commit();return renderToStaticMarkup(tree);},
  button(label){const button=nodes(tree).find(node=>node.type==="button"&&node.props.children===label);assert.ok(button,label);return button.props.onClick();},
  props(value){props={...props,...value};commit();},
  async settle(request,value,error=false){request[error?"reject":"resolve"](value);await Promise.resolve();await Promise.resolve();commit();},
  cleanup(){cleanup.forEach(fn=>fn?.());},
 };
}

test("copy and upload work with no task/API access, clipboard success is truthful, and failure offers manual copy",async()=>{
 const prior=Object.getOwnPropertyDescriptor(globalThis,"navigator");const writes=[],request=deferred();
 Object.defineProperty(globalThis,"navigator",{configurable:true,value:{clipboard:{writeText(text){writes.push(text);return request.promise;}}}});
 const f=fixture("ReportFollowUpActions",{reportId,requirementId,text:"保存的指导与提醒"});
 try{
  const upload=nodes(f.tree()).find(node=>node.props?.href?.startsWith("/portfolio?"));
  assert.ok(upload,"upload is a navigation link, not a task creation or analysis action");
  assert.equal(new URL(upload.props.href,"http://local.test").searchParams.get("sourceRequirement"),requirementId);
  assert.ok(f.html().includes("sourceReport="+reportId));
  assert.ok(!f.html().includes("已复制补证建议"));
  f.button("复制补证建议");await f.settle(request,null);
  assert.deepEqual(writes,["保存的指导与提醒"]);assert.ok(f.html().includes("已复制补证建议"));assert.equal(f.calls.length,0);
  globalThis.navigator.clipboard.writeText=async()=>{throw Error("denied");};
  f.button("复制补证建议");await Promise.resolve();await Promise.resolve();f.commit();
  assert.ok(f.html().includes("可手动复制的补证建议"));assert.equal(nodes(f.tree()).find(node=>node.type==="textarea").props.readOnly,true);
 }finally{f.cleanup();if(prior)Object.defineProperty(globalThis,"navigator",prior);else delete globalThis.navigator;}
});

test("late copy receipts cannot label a different identity/requirement's guidance as copied",async()=>{
 const prior=Object.getOwnPropertyDescriptor(globalThis,"navigator"),request=deferred();
 Object.defineProperty(globalThis,"navigator",{configurable:true,value:{clipboard:{writeText:()=>request.promise}}});
 const f=fixture("ReportFollowUpActions",{reportId,requirementId,text:"原指导"});
 try{
  f.button("复制补证建议");f.props({requirementId:reportId,text:"新指导"});
  await f.settle(request,null);assert.ok(!f.html().includes("已复制补证建议"));
 }finally{f.cleanup();if(prior)Object.defineProperty(globalThis,"navigator",prior);else delete globalThis.navigator;}
});

test("reanalysis preselection replaces only the matching version and carries the original comparison base",()=>{
 const report={id:reportId,jobId:"33333333-3333-3333-3333-333333333333",materials:[
  {kind:"resume",id:"44444444-4444-4444-4444-444444444444"},
  {kind:"project",id:"55555555-5555-5555-5555-555555555555"},
  {kind:"project",id:"66666666-6666-6666-6666-666666666666"},
 ]};
 const resume=helpers.reportReanalysisHref(report,{kind:"resume",versionId:"77777777-7777-7777-7777-777777777777"});
 assert.ok(resume);const rq=new URLSearchParams(resume.split("?")[1]);
 assert.equal(rq.get("compareTo"),reportId);assert.equal(rq.get("resumeVersionId"),"77777777-7777-7777-7777-777777777777");
 assert.deepEqual(rq.getAll("projectVersionId"),["55555555-5555-5555-5555-555555555555","66666666-6666-6666-6666-666666666666"]);
 const replaced=helpers.reportReanalysisHref(report,{kind:"project",versionId:"88888888-8888-8888-8888-888888888888"},{versionIds:["55555555-5555-5555-5555-555555555555","88888888-8888-8888-8888-888888888888"]});
 assert.ok(replaced);const pq=new URLSearchParams(replaced.split("?")[1]);
 assert.deepEqual(pq.getAll("projectVersionId"),["88888888-8888-8888-8888-888888888888","66666666-6666-6666-6666-666666666666"]);
 assert.equal(helpers.reportReanalysisHref(report,{kind:"project",versionId:"88888888-8888-8888-8888-888888888888"}),null,"a URL hint cannot replace the missing owned project history");
});

test("a first or different project is added without replacing a prior report selection",()=>{
 const resume="44444444-4444-4444-4444-444444444444";
 const previous="55555555-5555-5555-5555-555555555555";
 const uploaded={kind:"project",versionId:"88888888-8888-8888-8888-888888888888"};
 const report={id:reportId,jobId:"33333333-3333-3333-3333-333333333333",materials:[{kind:"resume",id:resume}]};
 const project={versionIds:[uploaded.versionId],sourceVersionId:previous};
 for(const projectIds of [[],[previous]]){
  const base={...report,materials:[...report.materials,...projectIds.map(id=>({kind:"project",id}))]};
  const url=new URL(helpers.reportReanalysisHref(base,uploaded,project,requirementId),"http://local.test");
  assert.equal(url.searchParams.get("compareTo"),reportId);
  assert.equal(url.searchParams.get("sourceRequirement"),requirementId);
  assert.equal(url.searchParams.get("resumeVersionId"),resume);
  assert.deepEqual(url.searchParams.getAll("projectVersionId"),[...projectIds,uploaded.versionId]);
 }
});
test("report upload hints accept only UUID context, never return URLs or version selection instructions",()=>{
 assert.deepEqual(helpers.reportFollowUpContext(query()),{reportId,requirementId});
 for(const bad of ["https://evil.test","../../other","javascript:alert(1)","bad#fragment"]) {
  assert.equal(helpers.reportFollowUpContext(new URLSearchParams({sourceReport:bad,sourceRequirement:requirementId})),null);
  assert.equal(helpers.reportUploadHref(bad,requirementId),"/portfolio");
 }
 const href=helpers.reportUploadHref(reportId,requirementId);
 assert.ok(href.startsWith("/portfolio?"));assert.ok(!href.includes("selected")&&!href.includes("analyze"));
});

test("upload return verifies the saved report and exposes navigation only, preserving existing materials",async()=>{
 const env={query:query()};const f=fixture("ReportUploadReturn",{},env);
 const report={id:reportId,jobId:"33333333-3333-3333-3333-333333333333",jobTitle:"原岗位",items:[{requirementId,requirementTitle:"原要求"}],materials:[{id:"fixed-old-version"}]};const before=JSON.stringify(report);
 try{
  assert.deepEqual(f.calls,[reportId]);await f.settle(f.requests[0],report);
  const html=f.html();assert.ok(html.includes(`/reports/${reportId}#requirement-${requirementId}`));assert.ok(html.includes(`/jobs/${report.jobId}`));
  assert.ok(!html.includes("本次上传已保存"));
  f.props({uploaded:{kind:"project",versionId:"new-version"}});
  assert.ok(f.html().includes("本次上传仍在处理中")||f.html().includes("尚未找到本次上传版本")||f.html().includes("正在核对本次上传状态"));
  assert.equal(f.calls.length,1);assert.equal(JSON.stringify(report),before);
 }finally{f.cleanup();}
});

test("ready state is bound to the current report/kind/version and a delayed B never borrows A's completion",async()=>{
 const versionA="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",versionB="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
 const lists=deferred();const env={query:new URLSearchParams({sourceReport:reportId,sourceRequirement:requirementId}),lists:()=>lists.promise};
 const f=fixture("ReportUploadReturn",{},env);const report={id:reportId,jobId:"33333333-3333-3333-3333-333333333333",items:[{requirementId,requirementTitle:"原要求"}],materials:[{id:"44444444-4444-4444-4444-444444444444",kind:"resume",versionNumber:1}]};
 const flush=async()=>{await new Promise(r=>setTimeout(r,0));f.commit();};
 try{
  await f.settle(f.requests[0],report);
  f.props({uploaded:{kind:"resume",versionId:versionA}});await flush();
  lists.resolve([{id:"a-resume",title:"A",versions:[{id:versionA,versionNumber:1,status:"completed"}]}]);
  await flush();assert.ok(f.html().includes("使用新版材料重新分析"),f.html().slice(0,500));
  const listsB=deferred();env.lists=()=>listsB.promise;
  f.props({uploaded:{kind:"resume",versionId:versionB}});await flush();
  assert.ok(!f.html().includes("使用新版材料重新分析"),"B must not inherit A's ready state");
  listsB.resolve([{id:"b-resume",title:"B",versions:[{id:versionB,versionNumber:1,status:"processing"}]}]);
  await flush();assert.ok(!f.html().includes("使用新版材料重新分析"),"processing B is not analyzable");
  assert.ok(f.html().includes("仍在处理中"));
  const listsReady=deferred();env.lists=()=>listsReady.promise;
  f.props({uploaded:{kind:"resume",versionId:versionB}});await flush();
  listsReady.resolve([{id:"b-resume",title:"B",versions:[{id:versionB,versionNumber:1,status:"completed"}]}]);
  await flush();assert.ok(f.html().includes("使用新版材料重新分析"),"B opens only after its own completion");
 }finally{f.cleanup();}
});
test("completed upload offers a version-replacing reanalysis link that keeps the original report as comparison base",async()=>{
 const oldProject="77777777-7777-7777-7777-777777777777", otherProject="88888888-8888-8888-8888-888888888888";
 const env={query:new URLSearchParams({sourceReport:reportId,sourceRequirement:requirementId,sourceProjectVersion:oldProject}),projects:[{id:"project-resource",name:"项目",versions:[{id:oldProject,versionNumber:1,status:"completed"},{id:"99999999-9999-9999-9999-999999999999",versionNumber:3,status:"completed",createdAt:"2026-11-07T00:00:00Z",originalFilename:"new.zip"}]}]};
 const f=fixture("ReportUploadReturn",{},env);
 const report={id:reportId,jobId:"33333333-3333-3333-3333-333333333333",jobTitle:"原岗位",items:[{requirementId,requirementTitle:"原要求"}],materials:[{id:"44444444-4444-4444-4444-444444444444",kind:"resume",versionNumber:1},{id:oldProject,kind:"project",versionNumber:1},{id:otherProject,kind:"project",versionNumber:2}]};
 try{
  await f.settle(f.requests[0],report);
  f.props({uploaded:{kind:"project",versionId:"99999999-9999-9999-9999-999999999999"}});
  await new Promise(resolve=>setTimeout(resolve,0));f.commit();
  const html=f.html();assert.ok(html.includes("使用新版材料重新分析"));assert.ok(!html.includes("本次上传仍在处理中"));
  const link=html.match(/href="([^"]*\/jobs\/[^"]*)"/)?.[1]??"";
  const url=new URL(link.replaceAll("&amp;","&"),"http://local.test");
  assert.equal(url.searchParams.get("compareTo"),reportId);
  assert.equal(url.searchParams.get("sourceRequirement"),requirementId);
  assert.equal(url.searchParams.get("resumeVersionId"),"44444444-4444-4444-4444-444444444444");
  assert.deepEqual(url.searchParams.getAll("projectVersionId"),["99999999-9999-9999-9999-999999999999",otherProject]);
 }finally{f.cleanup();}
});
test("denied, missing requirements and late upload-context replies never expose another report's navigation",async()=>{
 const env={query:query()},f=fixture("ReportUploadReturn",{},env);
 try{
  await f.settle(f.requests[0],Error("无权访问原报告"),true);
  assert.ok(f.html().includes("无权访问原报告"));assert.ok(!f.html().includes("到原岗位选择"));
  f.button("重试读取原报告");f.commit();
  env.query=new URLSearchParams({sourceReport:requirementId,sourceRequirement:reportId});f.commit();
  await f.settle(f.requests[2],{jobTitle:"新报告",jobId:reportId,items:[]});
  await f.settle(f.requests[1],{jobTitle:"旧回执",jobId:requirementId,items:[{requirementId,requirementTitle:"旧要求"}]});
  assert.ok(f.html().includes("未找到对应要求"));assert.ok(!f.html().includes("旧回执"));
 }finally{f.cleanup();}
});

test("invalid context or the existing growth-task path causes no report lookup or new return workflow",()=>{
 for(const params of [new URLSearchParams(),new URLSearchParams({sourceReport:"bad",sourceRequirement:requirementId}),new URLSearchParams({...Object.fromEntries(query()),growthTask:reportId})]){
  const f=fixture("ReportUploadReturn",{}, {query:params});try{assert.equal(f.tree(),null);assert.equal(f.calls.length,0);}finally{f.cleanup();}
 }
});

test("the original job form explicitly submits chosen new versions without creating or binding a growth task",async()=>{
 const values=[],sent=[],navigated=[],submitting={current:false};let index=0;
 const resumes=[{id:"resume",title:"简历",versions:[{id:"new-resume",versionNumber:2,status:"completed"}]}];
 const projects=[{id:"project",name:"项目",versions:[{id:"old-project",versionNumber:1,status:"completed"},{id:"new-project",versionNumber:2,status:"completed"}]}];
 const frozen=JSON.stringify({resumes,projects});
 const ResumePicker=()=>null,ProjectPicker=()=>null;
 const modules={"@/lib/demo-display-identity.js":demoPresentation,
  react:{useEffect(){},useMemo:fn=>fn(),useRef:()=>submitting,useState(initial){const i=index++;if(!(i in values))values[i]=i===0?resumes:i===1?projects:i===6?false:initial;return[values[i],value=>{values[i]=typeof value==="function"?value(values[i]):value;}];}},
  "react/jsx-runtime":require("react/jsx-runtime"),"next/link":{__esModule:true,default:()=>null},
  "next/navigation":{useRouter:()=>({push:value=>navigated.push(value)})},
  "@/lib/api/client":{errorMessage:String,api:new Proxy({async createMatch(payload){sent.push(payload);return{taskId:"new-analysis"};}},{get(target,key){if(key in target)return target[key];return()=>{throw Error(`unexpected API ${String(key)}`);};}})},
  "@/lib/api/domain":{},"@/lib/application-display":{},
  "@/lib/job-application-status":{createJobApplicationStatusSession:()=>({})},
  "@/lib/recommendation-selection":{},"@/lib/task-navigation":taskNavigation,"./AuthProvider":{},"./AccessGate":{__esModule:true,default:()=>null,ErrorNotice:()=>null},
  "./ProjectVersionPicker":{__esModule:true,default:ProjectPicker},"./ResumeVersionPicker":{__esModule:true,default:ResumePicker},"./ScenarioMaterials":{__esModule:true,default:()=>null},
 };
 const source=readFileSync(new URL("../src/components/JobDetailView.tsx",import.meta.url),"utf8");
 const code=transform(source+"\nexport { MatchForm };",{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code;
 const mod={exports:{}};new Function("require","module","exports",code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
 const render=()=>{index=0;return mod.exports.MatchForm({job:{id:reportId,requirements:[]},initialResumeVersionId:"",initialProjectVersionIds:[]});};
 const submit=tree=>nodes(tree).find(node=>node.type==="form").props.onSubmit({preventDefault(){}});
 let tree=render();await submit(tree);assert.equal(sent.length,0,"no matching request before choosing a resume");
 nodes(tree).find(node=>node.type===ResumePicker).props.onChange("new-resume");
 nodes(tree).find(node=>node.type===ProjectPicker).props.onChange(["new-project"]);
 tree=render();assert.equal(sent.length,0,"changing selections must not start analysis");
 await submit(tree);
 assert.deepEqual(sent,[{jobId:reportId,resumeVersionId:"new-resume",projectVersionIds:["new-project"],externalAiConsent:false,usePreviousReport:false}]);
 assert.deepEqual(navigated,["/tasks/new-analysis"]);
 assert.equal(JSON.stringify({resumes,projects}),frozen);
 for(const route of ["portfolio/page.tsx","jobs/[id]/page.tsx","reports/[id]/page.tsx","tasks/[id]/page.tsx","growth/page.tsx","growth/[id]/page.tsx"]){
  assert.ok(existsSync(new URL(`../src/app/${route}`,import.meta.url)),route);
 }
});


