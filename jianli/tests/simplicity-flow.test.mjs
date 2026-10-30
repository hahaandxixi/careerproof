import test, { afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createApplicationListSession } from "../src/lib/application-list-session.ts";
import { createRefreshGate } from "../src/lib/refresh-gate.ts";
const require=createRequire(import.meta.url), React=require("react"), {transform}=require("sucrase");
const oldDocument=globalThis.document,oldWindow=globalThis.window;
afterEach(()=>{globalThis.document=oldDocument;globalThis.window=oldWindow;});
const nodes=n=>!n||typeof n!=="object"?[]:[n,...React.Children.toArray(n.props?.children).flatMap(nodes)];
const text=n=>typeof n==="string"?n:React.Children.toArray(n?.props?.children).map(text).join("");
function mount(filename, additions, props={}, unwrap=true) {
 const cells=[],effects=[];let cursor=0;
 const same=(a,b)=>a&&a.length===b.length&&a.every((v,i)=>Object.is(v,b[i]));
 const memo=(fn,deps)=>{const i=cursor++;if(!cells[i]||!same(cells[i].deps,deps))cells[i]={deps,value:fn()};return cells[i].value;};
 const hooks={useState(value){const i=cursor++;if(!(i in cells))cells[i]=value;return[cells[i],v=>{cells[i]=typeof v==="function"?v(cells[i]):v;}];},useRef(value){const i=cursor++;return cells[i]??={current:value};},useMemo:memo,useCallback:(fn,deps)=>memo(()=>fn,deps),useEffect(fn,deps){const i=cursor++;if(!cells[i]||!same(cells[i].deps,deps)){const cleanup=cells[i]?.cleanup;cells[i]={deps};effects.push(()=>{cleanup?.();cells[i].cleanup=fn();});}}};
 globalThis.document=Object.assign(new EventTarget(),{visibilityState:"visible"});globalThis.window=new EventTarget();
 const modules={react:hooks,"react/jsx-runtime":require("react/jsx-runtime"),"next/link":{__esModule:true,default:p=>React.createElement("a",p)},"./AuthProvider":{useAuth:()=>({user:{id:"student"}})},"./AccessGate":{__esModule:true,default:()=>null},"./ListPagination":{__esModule:true,default:()=>null},...additions};
 const code=transform(readFileSync(new URL(`../src/components/${filename}.tsx`,import.meta.url),"utf8"),{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code;
 const mod={exports:{}};new Function("require","module","exports",code)(name=>{assert.ok(name in modules,name);return modules[name];},mod,mod.exports);
 const render=()=>{cursor=0;const parent=mod.exports.default(props);return !unwrap?parent:parent.props.children?.type?parent.props.children.type(parent.props.children.props):parent.type(parent.props);};
 return {render,async settle(){let tree;for(let i=0;i<15;i++){tree=render();while(effects.length)effects.shift()();await Promise.resolve();}return tree;}};
}
test("application status applies immediately with query and pagination reset; search has a stable accurate action name",async()=>{
 const calls=[];
 const h=mount("ApplicationList",{"@/lib/api/client":{api:{myApplications:async(page,size,_,filters)=>{calls.push({page,...filters});return{items:[],total:0,page,pageSize:size};},withdrawApplication:()=>assert.fail("no mutation")},errorMessage:String},"@/lib/notification-session":{applicationAnchorId:()=>null,includeApplicationTarget:async rows=>rows,clearApplicationAnchor(){}},"@/lib/application-anchor":{createApplicationAnchorRevealer:()=>({attempt(){}})},"@/lib/application-list-session":{createApplicationListSession},"@/lib/refresh-gate":{createRefreshGate},"@/lib/application-display":{applicationEventsSummary:String,applicationNextAction:String,applicationReplyText:String,applicationStatusText:String}});
 let tree=await h.settle();nodes(tree).find(n=>n.type==="input").props.onChange({target:{value:"Python"}});tree=h.render();
 nodes(tree).find(n=>n.type==="button"&&text(n)==="待我核对").props.onClick();tree=await h.settle();
 assert.deepEqual(calls.at(-1),{page:1,q:"Python",view:"action"});
 assert.equal(nodes(tree).find(n=>n.type==="button"&&text(n)==="待我核对").props["aria-pressed"],true);
 assert.ok(nodes(tree).some(n=>n.type==="button"&&text(n)==="搜索"));assert.ok(!nodes(tree).some(n=>n.type==="select"));
 nodes(tree).find(n=>n.type==="button"&&text(n)==="重置").props.onClick();await h.settle();assert.deepEqual(calls.at(-1),{page:1,q:"",view:"all"});
});
test("legacy task URL only reads saved records and clears private content on hide",async()=>{
 const task={id:"t",baseReportId:"r",jobTitle:"Python",requirementId:"q",requirementTitle:"接口",gap:"缺运行记录",originalAction:"运行测试",plan:{deliverable:"记录",steps:[],acceptanceChecks:[]},materials:[],comparison:null};let reads=0;
 const api=new Proxy({growthTask:async()=>{reads++;return task;},getAnswerDraft:async()=>({text:"私人历史草稿"})},{get(target,key){if(key in target)return target[key];assert.fail(`unexpected API ${String(key)}`);}});
 const h=mount("GrowthHistory",{"@/lib/api/client":{api,errorMessage:String},"./GrowthComparison":{__esModule:true,default:()=>null}},{id:"t"});
 let tree=await h.settle();assert.match(text(tree),/缺运行记录/);assert.match(text(tree),/私人历史草稿/);
 assert.deepEqual(nodes(tree).filter(n=>n.type==="button").map(text),["刷新"]);
 document.visibilityState="hidden";document.dispatchEvent(new Event("visibilitychange"));assert.equal(h.render(),null);
 document.visibilityState="visible";document.dispatchEvent(new Event("visibilitychange"));tree=await h.settle();assert.match(text(tree),/私人历史草稿/);assert.equal(reads,2);
});

test("upload navigation resolves only a currently owned project version and opens a form once",async()=>{
 let query=new URLSearchParams({add:"project",sourceProjectVersion:"version-a"});const opened=[];
 const props={ready:true,projects:[{id:"owned",versions:[{id:"version-a"}]}],onOpen:id=>{opened.push(id);return true;}};
 const h=mount("MaterialUploadIntent",{"next/navigation":{useSearchParams:()=>query}},props,false);
 await h.settle();await h.settle();assert.deepEqual(opened,["owned"]);
 query=new URLSearchParams({add:"project",sourceProjectVersion:"foreign"});const tree=await h.settle();
 assert.deepEqual(opened,["owned"]);assert.match(text(tree),/原项目不在当前材料库/);
});
test("pending uploads are kept instead of being overwritten by a navigation hint",async()=>{
 const h=mount("MaterialUploadIntent",{"next/navigation":{useSearchParams:()=>new URLSearchParams({add:"project"})}},{ready:true,projects:[],onOpen:()=>false},false);
 assert.match(text(await h.settle()),/未完成的上传/);
});
