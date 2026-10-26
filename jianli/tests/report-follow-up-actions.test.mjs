import test from "node:test";
import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
import { readFileSync } from "node:fs";
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
 const modules={react,"react/jsx-runtime":require("react/jsx-runtime"),"next/link":{__esModule:true,default:props=>React.createElement("a",props)},
  "next/navigation":{useSearchParams:()=>environment.query??new URLSearchParams()},
  "@/lib/report-follow-up":helpers,"@/lib/api/client":{errorMessage:error=>error.message,api:{getReport(id){calls.push(id);const request=deferred();requests.push(request);return request.promise;}}}};
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
  assert.ok(f.html().includes("不必创建补证记录"));
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
  assert.ok(f.html().includes("请确认处理完成"));assert.ok(f.html().includes("明确选择需要分析的简历与项目版本"));
  assert.equal(f.calls.length,1);assert.equal(JSON.stringify(report),before);
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
