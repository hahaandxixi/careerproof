import * as reportNavigation from "../src/lib/report-navigation.ts";
import * as materialReportLinks from "../src/lib/material-report-link.ts";
import * as evidenceWorkspace from "../src/lib/evidence-workspace.ts";
import * as sourceLabels from "../src/lib/source-label.ts";
import * as demoPresentation from "../src/lib/demo-display-identity.js";
import test from "node:test";
import assert from "node:assert/strict";
import {createRequire, registerHooks} from "node:module";
import {readFileSync} from "node:fs";
import {createReportReviewSession,initialReportReviewState} from "../src/lib/report-review-session.ts";
const require=createRequire(import.meta.url),React=require("react"),{transform}=require("sucrase"),jsx=require("react/jsx-runtime"),{renderToStaticMarkup}=require("react-dom/server");
const resolution = registerHooks({resolve(specifier, context, next) {
 if (specifier.startsWith("./") && !/\.[jt]s$/.test(specifier)) {
   return next(specifier + ".ts", context);
 }
 return next(specifier, context);
}});
const workspace = await import("../src/lib/report-workspace.ts");
const {reportEntryRequirement} = await import("../src/lib/report-reader.ts");
resolution.deregister();
const nodes=n=>!n||typeof n!=="object"?[]:[n,...React.Children.toArray(n.props?.children).flatMap(nodes),...(n.props?.sections??[]).flatMap(s=>nodes(s.content))];
const text=n=>typeof n==="string"?n:[...React.Children.toArray(n?.props?.children),...(n?.props?.sections??[]).map(s=>s.content)].map(text).join("");
function fixture({writeError,readError,search="",hash="",differentStatus=false,materials=[]}={}){
 const cells=[],effects=[];let cursor=0,reads=0,writes=0,hashEvents=0,account="owner",role="student";
 const savedWindow=globalThis.window;const listeners={};
 globalThis.window={location:{href:"http://localhost/reports/r"+search+hash,hash,search},history:{state:{__NA:true},pushState(_state,_unused,url){Object.assign(globalThis.window.location,{href:url.href,hash:url.hash,search:url.search});}},dispatchEvent(event){if(event.type==="hashchange")hashEvents++;for(const fn of listeners[event.type]??[])fn(event);},addEventListener(type,fn){(listeners[type]??=[]).push(fn);},removeEventListener(type,fn){listeners[type]=(listeners[type]??[]).filter(value=>value!==fn);}};
 const memo=(fn,deps)=>{const i=cursor++;if(!cells[i]||cells[i].deps.join()!==deps.join())cells[i]={deps,value:fn()};return cells[i].value;};
 const hooks={useState(initial){const i=cursor++;if(!(i in cells))cells[i]=initial;return[cells[i],v=>{cells[i]=typeof v==="function"?v(cells[i]):v;}];},useMemo:memo,useEffect(fn,deps){const i=cursor++;const previous=cells[i];if(!previous||JSON.stringify(previous.deps)!==JSON.stringify(deps)){cells[i]={deps};effects.push(()=>cells[i].cleanup=fn());}}};
 const report={id:"r",items:["a","b"].map(requirementId=>({requirementId,requirementTitle:requirementId,verdict:differentStatus && requirementId==="b"?"gap":"supported",evidenceId:"e",evidenceList:[],confirmationStatus:"pending",reviewerNote:"saved note"})),materials,analysisMode:"rules",actionPlan:[],aiToolCalls:[]};
 const api={getReport:async()=>{reads++;if(reads===2&&readError)throw readError;return report;},reviewEvidence:async(...args)=>{writes++;if(writeError)throw writeError;return args;}};
 const stub=()=>null;const radarProps=[],heatmapProps=[],workspaceProps=[];const Radar=props=>{radarProps.push(props);return null;};const Workspace=props=>{workspaceProps.push(props);return React.createElement(React.Fragment,null,props.overview,props.children);};const modules={"./SkillRadar":{__esModule:true,default:Radar},"@/lib/evidence-anchor":{navigateEvidenceFragment:()=>{}},"next/navigation":{useSearchParams:()=>new URLSearchParams()},"@/lib/evidence-workspace":evidenceWorkspace,"@/lib/source-label":sourceLabels,"@/lib/demo-display-identity.js":demoPresentation,react:hooks,"react/jsx-runtime":jsx,"next/link":{__esModule:true,default:stub},"@/lib/api/client":{api,errorMessage:e=>e.message},"@/lib/report-review-session":{createReportReviewSession,initialReportReviewState},"./AuthProvider":{useAuth:()=>({user:{id:account,role}})},"./AccessGate":{__esModule:true,default:stub,ErrorNotice:stub},"@/lib/analysis-status":{sourceContextVerified:()=>true},"@/lib/report-display":{reportAiRatedCount:()=>0},"@/lib/agent-evidence":{agentProcessSummary:()=>""},"@/lib/report-workspace":workspace,"@/lib/material-report-link":materialReportLinks,"@/lib/heatmap-cell.js":{heatmapCellClass:()=>""},"@/lib/report-reader":{initialReportRequirement:items=>items[0]?.requirementId??"",reportEntryRequirement}};
 modules["@/lib/report-navigation"]=reportNavigation;
 modules["@/lib/report-follow-up"]={followUpCopyText:()=>""};
 for(const name of ["SourceCoverage","EvidenceLink","EvidenceAnchorRestore","ReportComparisonPanel","McpAccessPanel","ApplicationSubmit","ReportAgentEvidence","ReportAiExplanation","ReportSourcePanel","ReportSections","ReportPaperHeader","ReportFollowUpActions","PracticeEntry","ReportCareerAdvice"])modules[`./${name}`]={__esModule:true,default:stub};
 modules["./ProjectFileReader"]={__esModule:true,default:({id})=>React.createElement("div",{"data-project-version":id})};
 modules["./ReportRequirementHeatmap"]={__esModule:true,default:props=>{heatmapProps.push(props);return null;}};
 modules["./ReportSections"]={__esModule:true,default:({header,sections})=>React.createElement(React.Fragment,null,header,sections?.[0]?.content)};
 modules["./ReportEvidenceWorkspace"]={__esModule:true,default:Workspace,RequirementActionPanel:stub};
 modules["./RequirementSupplement"]={__esModule:true,RequirementSupplementJump:stub,RequirementSupplementTarget:stub};
 const source=readFileSync(new URL("../src/components/ReportDetail.tsx",import.meta.url),"utf8")+`
export {ReportWorkspace};`;
 const mod={exports:{}};new Function("require","module","exports",transform(source,{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
 const render=()=>{cursor=0;return mod.exports.ReportWorkspace({id:"r"});};
 return {radarProps,heatmapProps,workspaceProps,render,html(){return renderToStaticMarkup(this.render());},async settle(){for(let i=0;i<10;i++){render();while(effects.length)effects.shift()();await Promise.resolve();}return render();},navigate(hash){globalThis.window.location.hash=hash;(listeners.hashchange??[]).forEach(fn=>fn());},get reads(){return reads;},get writes(){return writes;},get hashEvents(){return hashEvents;},dispose(){for(const c of cells)c?.cleanup?.();globalThis.window=savedWindow;},outer(id){return mod.exports.default({id});},setAccount(id){account=id;},setRole(value){role=value;}};
}

test("filter changes update selection and URL without triggering anchor navigation", async () => {
 const h=fixture({differentStatus:true});
 try {
  await h.settle(); h.html();
  h.workspaceProps.at(-1).onFilterChange("supported"); await h.settle(); h.html();
  assert.equal(h.workspaceProps.at(-1).selectedRequirementId,"a");
  h.workspaceProps.at(-1).onFilterChange("gaps"); await h.settle(); h.html();
  assert.equal(h.workspaceProps.at(-1).selectedRequirementId,"b");
  assert.equal(h.radarProps.at(-1).selectedRequirementId,"b");
  assert.equal(globalThis.window.location.hash,"");
  assert.equal(globalThis.window.location.search,"?filter=gaps&requirement=b");
  h.workspaceProps.at(-1).onFilterChange("all"); await h.settle(); h.html();
  assert.equal(h.workspaceProps.at(-1).selectedRequirementId,"b");
  h.workspaceProps.at(-1).onFilterChange("other"); await h.settle(); h.html();
  assert.equal(h.workspaceProps.at(-1).selectedRequirementId,null);
  assert.equal(globalThis.window.location.hash,"");
  assert.equal(globalThis.window.location.search,"?filter=other&requirement=");
  h.workspaceProps.at(-1).onFilterChange("all"); await h.settle(); h.html();
  assert.equal(h.workspaceProps.at(-1).selectedRequirementId,"a");
  assert.equal(h.hashEvents,0);
 } finally { h.dispose(); }
});
test("report radar is wired to the shared active requirement, not a constant empty id", () => {
 const source = readFileSync(new URL("../src/components/ReportDetail.tsx", import.meta.url), "utf8");
 assert.match(source, /const radarRequirementId = activeRequirementId === undefined \? initialReportRequirement\(report\.items\) : activeRequirementId/);
 assert.match(source, /initialRequirementId=\{radarRequirementId\}/);
 assert.match(source, /selectedRequirementId=\{radarRequirementId\}/);
 assert.doesNotMatch(source, /initialRequirementId=""/);
});
test("reloading a report section restores the URL requirement for the reader and radar", async () => {
 const h=fixture({search:"?filter=all&requirement=b",hash:"#report-matching"});
 try {
  await h.settle(); h.html();
  assert.equal(h.workspaceProps.at(-1).selectedRequirementId,"b");
  assert.equal(h.radarProps.at(-1).selectedRequirementId,"b");
  assert.equal(h.heatmapProps.at(-1).selectedRequirementId,"b");
  h.navigate("#requirement-a"); await h.settle(); h.html();
  assert.equal(h.workspaceProps.at(-1).selectedRequirementId,"a");
  h.navigate("#report-matching"); await h.settle(); h.html();
  assert.equal(h.workspaceProps.at(-1).selectedRequirementId,"b");
 } finally { h.dispose(); }
});
test("hash selection drives heatmap and radar with one requirement id, not a stale radar highlight", async () => {
 const h=fixture(); await h.settle(); h.html();
 assert.equal(h.radarProps.at(-1).initialRequirementId,"a");
 assert.equal(h.heatmapProps.at(-1).selectedRequirementId,"a");
 h.navigate("#requirement-b"); await h.settle(); h.html();
 assert.equal(h.radarProps.at(-1).initialRequirementId,"b");
 assert.equal(h.radarProps.at(-1).selectedRequirementId,"b");
 assert.equal(h.heatmapProps.at(-1).selectedRequirementId,"b");
 h.navigate("#report-matching"); await h.settle(); h.html();
 assert.equal(h.radarProps.at(-1).initialRequirementId,"b");
 h.navigate("#requirement-a"); await h.settle(); h.html();
 assert.equal(h.radarProps.at(-1).initialRequirementId,"a");
 h.dispose();
});
test("write failure keeps the actual report tree and unsaved note, with a local error",async()=>{
 const h=fixture({writeError:Object.assign(new Error("rejected"),{status:409})});let tree=await h.settle();
 const area=nodes(tree).find(n=>n.type==="textarea");area.props.onChange({target:{value:"unsaved private edit"}});tree=h.render();
 await nodes(tree).find(n=>n.type==="button"&&text(n)==="采纳证据").props.onClick();tree=await h.settle();
 assert.equal(tree.type,"div");assert.equal(nodes(tree).filter(n=>n.type==="article").length,2);assert.equal(nodes(tree).find(n=>n.type==="textarea").props.value,"unsaved private edit");assert.match(text(tree),/核对未保存/);h.dispose();
});
test("read failure after saving exposes a read-only recovery while all review writes are blocked",async()=>{
 const h=fixture({readError:new Error("offline")});let tree=await h.settle();await nodes(tree).find(n=>n.type==="button"&&text(n)==="采纳证据").props.onClick();tree=await h.settle();
 assert.equal(tree.type,"div");assert.match(text(tree),/核对已保存/);assert.ok(nodes(tree).filter(n=>n.type==="button"&&text(n)==="采纳证据").every(n=>n.props.disabled));
 await nodes(tree).find(n=>n.type==="button"&&text(n)==="重新读取核对记录").props.onClick();tree=await h.settle();assert.equal(h.writes,1);assert.equal(h.reads,3);assert.ok(nodes(tree).filter(n=>n.type==="button"&&text(n)==="采纳证据").every(n=>!n.props.disabled));h.dispose();
});
test("account, role and report keys establish separate workspaces",()=>{
 const h=fixture();const a=h.outer("r").props.children.key;h.setAccount("other");const b=h.outer("r").props.children.key;const c=h.outer("other-report").props.children.key;assert.notEqual(a,b);assert.notEqual(b,c);h.setRole("admin");assert.notEqual(c,h.outer("other-report").props.children.key);
});

test("one shared requirement index owns filtering and an empty category cannot revive a reply link", async () => {
 const h=fixture({search:"?enterpriseReply=b"});
 try {
   h.setRole("admin");
   await h.settle(); h.html();
   assert.equal(h.workspaceProps.at(-1).selectedRequirementId,"b");
   h.workspaceProps.at(-1).onFilterChange("other");
   h.navigate("#report-matching");
   await h.settle(); h.html();
   assert.equal(h.workspaceProps.at(-1).filter,"other");
   assert.equal(h.workspaceProps.at(-1).selectedRequirementId,null);
   h.navigate("#requirement-b");
   await h.settle(); h.html();
   assert.equal(h.workspaceProps.at(-1).filter,"all");
   assert.equal(h.workspaceProps.at(-1).selectedRequirementId,"b");
 } finally { h.dispose(); }
});


test("fixed material readers bind the reported project version and only mount for students", async () => {
 const h=fixture({materials:[
   {kind:"project",id:"fixed-v1",title:"Fixed project",versionNumber:1},
   {kind:"resume",id:"resume-v2",title:"Fixed resume",versionNumber:2},
 ]});
 try {
   await h.settle();
   const html=()=>renderToStaticMarkup(h.render().props.children.props.sections.find(s=>s.id==="report-materials").content);
   assert.match(html(), /data-project-version="fixed-v1"/);
   assert.doesNotMatch(html(), /data-project-version="resume-v2"|预览此固定版本/);
   for(const role of ["admin","enterprise"]) {
     h.setRole(role);
     assert.doesNotMatch(html(), /data-project-version/);
   }
 } finally { h.dispose(); }
});
