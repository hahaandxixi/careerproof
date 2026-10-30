// Execute the real Workspace/event handlers with deterministic hooks and API
// promises. These are component behavior tests, not real browser visibility.
import test, { afterEach } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { createApplicationBoardSession, initialApplicationBoardState } from "../src/lib/application-board-session.ts";
import { evidenceWorkspace } from "../src/lib/evidence-workspace.ts";
import { createRefreshGate } from "../src/lib/refresh-gate.ts";
import { createApplicationAnchorRevealer } from "../src/lib/application-anchor.ts";
import { invalidNarrativeCitations, readableCitationText } from "../src/lib/report-citations.ts";

const require=createRequire(import.meta.url),React=require("react"),{transform}=require("sucrase");
const originals=new Map(["window","document","location","requestAnimationFrame","cancelAnimationFrame"].map(k=>[k,globalThis[k]]));
const cleanups=[];
afterEach(()=>{while(cleanups.length)cleanups.pop()();for(const[k,v]of originals){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}});
const walk=node=>!node||typeof node!=="object"?[]:[node,...React.Children.toArray(node.props?.children).flatMap(walk)];
const text=node=>typeof node==="string"?node:React.Children.toArray(node?.props?.children).map(text).join("");

function fixture(count=2){
 const cells=[],effects=[],frames=new Map();let cursor=0,frame=0;
 const same=(a,b)=>a&&a.length===b.length&&a.every((v,i)=>Object.is(v,b[i]));
 const memo=(fn,deps)=>{const i=cursor++;if(!cells[i]||!same(cells[i].deps,deps))cells[i]={deps,value:fn()};return cells[i].value;};
 const hooks={useState(initial){const i=cursor++;if(!(i in cells))cells[i]=initial;return[cells[i],v=>{cells[i]=typeof v==="function"?v(cells[i]):v;}];},
  useRef(initial){const i=cursor++;return cells[i]??=( {current:initial});},useMemo:memo,useCallback:(fn,deps)=>memo(()=>fn,deps),
  useEffect(fn,deps){const i=cursor++;if(!cells[i]||!same(cells[i].deps,deps)){const old=cells[i]?.cleanup;cells[i]={deps};effects.push(()=>{old?.();cells[i].cleanup=fn();});}}};
 const win=new EventTarget(),doc=Object.assign(new EventTarget(),{visibilityState:"visible",getElementById:()=>null});
 globalThis.window=win;globalThis.document=doc;globalThis.location={hash:""};
 globalThis.requestAnimationFrame=fn=>{frames.set(++frame,fn);return frame;};globalThis.cancelAnimationFrame=id=>frames.delete(id);
 const counts={list:0,open:0,reply:0,detail:0};const queries=[];let authorized=true,waiter=null;
 const report={id:"report-a",summary:"合成固定报告",createdAt:"2026-10-27T00:00:00Z",items:[],materials:[],aiFallbackUsed:false};
 const row=id=>({id,jobId:"job-a",reportId:`report-${id}`,candidateName:`候选人${id}`,status:"viewed",replyKind:null,replyText:null,replyReferences:[],overallScore:10,events:[],comparisonBasis:"same",dimensions:[{requirementId:"r1",title:"Python要求",skill:"Python",score:10,verdict:"claimed_only",weight:1}]});
 const pageResult=()=>({items:[...(authorized?[row("a")]:[]),...Array.from({length:count-1},(_,i)=>row(String.fromCharCode(98+i)))],total:authorized?count:count-1,page:1,pageSize:20});
 const api={getJob:async()=>({id:"job-a",title:"测试岗位"}),jobApplications:async(_job,page,size,filters)=>{counts.list++;queries.push({page,size,...filters});return waiter?waiter:pageResult();},applicationDetail:async id=>{counts.detail++;if(id==="a"&&!authorized)throw Error("已撤回授权");return row(id);},
  openApplication:async id=>{counts.open++;return {...row(id),report:{...report,id:`report-${id}`}};},
  replyApplication:async()=>{counts.reply++;throw Error("test must not send");},downloadApplicationResume:async()=>{throw Error("test must not download");}};
 const stub=name=>Object.assign(()=>null,{testName:name});const Radar=stub("radar");
 const modules={"@/lib/report-citations":{invalidNarrativeCitations,readableCitationText},react:hooks,"react/jsx-runtime":require("react/jsx-runtime"),"next/dynamic":{default:()=>Radar,__esModule:true},"next/link":{default:stub("link"),__esModule:true},
  "./CandidatePairComparison":{default:stub("pair"),__esModule:true},"./SourceIdentity":{default:stub("source"),SourceIdentityDetails:stub("source-details"),__esModule:true},"./ListPagination":{default:stub("pagination"),__esModule:true},
  "@/lib/api/client":{api,errorMessage:e=>e.message},"@/lib/notification-session":{applicationAnchorId:()=>null,clearApplicationAnchor:()=>{},includeApplicationTarget:async rows=>rows},
  "@/lib/application-anchor":{createApplicationAnchorRevealer},"./AccessGate":{default:stub("gate"),__esModule:true},"./AuthProvider":{useAuth:()=>({user:{id:"enterprise-a"}})},
  "@/lib/application-comparison":{applicationFilterView:(items)=>({visible:items,empty:false,selectedOutside:false}),mixedComparisonBasis:()=>false},
  "@/lib/evidence-workspace":{evidenceWorkspace},"@/lib/evidence-display":{RULE_SCORE_CAP_NOTE:"规则说明",evidenceLevelName:String},"@/lib/report-display":{reportModeLabel:()=>"规则",reportSummaryText:String},
  "@/lib/heatmap-cell.js":{heatmapCellClass:()=>""},"@/lib/application-board-session":{createApplicationBoardSession,initialApplicationBoardState},"@/lib/refresh-gate":{createRefreshGate},
  "./ApplicationVerification":{default:stub("verification"),__esModule:true},"@/lib/verification-reply-draft":{activeVerificationReplyReferences:()=>[],appendVerificationReplyQuestion:()=>{}},
  "@/lib/verdict-display.js":{VERDICT_LABELS:{claimed_only:"仅简历声明"},APPLICATION_STATUS_LABELS:{viewed:"已查看"}}};
 const code=transform(readFileSync(new URL("../src/components/ApplicationBoard.tsx",import.meta.url),"utf8"),{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code;
 const mod={exports:{}};new Function("require","module","exports",code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
 const render=()=>{cursor=0;const outer=mod.exports.default({jobId:"job-a"});const tree=outer.props.children.type(outer.props.children.props);tree.props.ref.current={getBoundingClientRect:()=>({height:2400})};return tree;};
 const settle=async()=>{for(let i=0;i<25;i++){render();while(effects.length)effects.shift()();await Promise.resolve();}for(const[id,fn]of frames){frames.delete(id);fn();}return render();};
 cleanups.push(()=>cells.forEach(cell=>cell?.cleanup?.()));
 return{render,settle,counts,queries,Radar,nodes:walk,
  hide(){doc.visibilityState="hidden";doc.dispatchEvent(new Event("visibilitychange"));return render();},
  show(){doc.visibilityState="visible";doc.dispatchEvent(new Event("visibilitychange"));win.dispatchEvent(new Event("focus"));win.dispatchEvent(new Event("pageshow"));return render();},
  revoke(){authorized=false;},waitFor(value){waiter=value;},button(tree,label){const found=walk(tree).find(n=>n.type==="button"&&text(n)===label);assert.ok(found,label);return found;},
  radar(tree){return walk(tree).find(n=>n.type===Radar);}};
}

test("tab return restores radar requirement/evidence only after GET authorization and clears replies",async()=>{
 const h=fixture();let tree=await h.settle();h.button(tree,"候选人a").props.onClick();tree=await h.settle();
 h.radar(tree).props.onRequirementChange("r1");tree=h.render();h.radar(tree).props.onEvidenceExpandedChange(true);tree=h.render();
 h.nodes(tree).find(n=>n.type==="textarea").props.onChange({target:{value:"未发送的合成回复"}});tree=h.render();
 const confirm=h.nodes(tree).find(n=>n.type==="label"&&text(n).includes("我已核对正文"));h.nodes(confirm).find(n=>n.type==="input").props.onChange({target:{checked:true}});
 let resolve;h.waitFor(new Promise(yes=>{resolve=yes;}));tree=h.hide();assert.equal(h.radar(tree),undefined);assert.equal(tree.props.style.minHeight,2400);
 const reads=h.counts.list;tree=h.show();await Promise.resolve();assert.equal(h.radar(tree),undefined);
 resolve({items:[{id:"a",jobId:"job-a",reportId:"report-a",candidateName:"候选人a",status:"viewed",replyReferences:[],events:[],dimensions:[]}],total:1,page:1,pageSize:20});
 tree=await h.settle();assert.equal(h.radar(tree).props.initialRequirementId,"r1");assert.equal(h.radar(tree).props.evidenceExpanded,true);
 assert.equal(h.counts.open,1);assert.equal(h.counts.list,reads+1);assert.equal(h.counts.reply,0);
 assert.equal(h.nodes(tree).find(n=>n.type==="textarea").props.value,"");
 const confirmation=h.nodes(tree).find(n=>n.type==="label"&&text(n).includes("我已核对正文"));assert.equal(h.nodes(confirmation).find(n=>n.type==="input").props.checked,false);
});

test("comparison selection survives tab return and revoked candidates are pruned",async()=>{
 const h=fixture();let tree=await h.settle();
 for(const id of ["a","b"]){const th=h.nodes(tree).find(n=>n.type==="th"&&n.props.id===`application-${id}`);h.nodes(th).find(n=>n.type==="input").props.onChange();tree=await h.settle();}
 h.button(tree,"并排核对 2 位").props.onClick();tree=h.render();h.hide();h.show();tree=await h.settle();
 assert.equal(h.button(tree,"返回本页全部候选人").props["aria-pressed"],true);
 const checks=h.nodes(tree).filter(n=>n.type==="input"&&n.props.type==="checkbox");assert.equal(checks.filter(n=>n.props.checked).length,2);
 h.hide();h.revoke();h.show();tree=await h.settle();
 assert.ok(h.button(tree,"并排核对 1 位").props.disabled);assert.equal(h.counts.open,0);
});


test("three and four selected candidates retain the heatmap and offer only a two-person deep view",async()=>{
 const h=fixture(4);let tree=await h.settle();
 for(const id of ["a","b","c","d"]){if(id==="d"){h.button(tree,"返回本页全部候选人").props.onClick();tree=await h.settle();}const th=h.nodes(tree).find(n=>n.type==="th"&&n.props.id===`application-${id}`);h.nodes(th).find(n=>n.type==="input").props.onChange();tree=await h.settle();
 if(["c","d"].includes(id)){const count=id==="c"?3:4;h.button(tree,`并排核对 ${count} 位`).props.onClick();tree=await h.settle();assert.equal(h.nodes(tree).filter(n=>n.type==="th"&&n.props.id?.startsWith("application-")).length,count);h.button(tree,`双人对照（${count}）`).props.onClick();tree=h.render();const pair=h.nodes(tree).find(n=>Array.isArray(n.props?.candidates));assert.equal(pair.props.candidates.length,2);assert.equal(h.counts.open,0);h.button(tree,"候选人").props.onClick();tree=h.render();}}
 h.button(tree,"清空对照").props.onClick();tree=await h.settle();assert.ok(!h.nodes(tree).some(n=>Array.isArray(n.props?.candidates)));
});

test("enterprise status and evidence filters apply immediately while retaining cross-page comparison",async()=>{
 const h=fixture();let tree=await h.settle();
 const th=h.nodes(tree).find(n=>n.type==="th"&&n.props.id==="application-a");h.nodes(th).find(n=>n.type==="input").props.onChange();tree=await h.settle();
 h.nodes(tree).find(n=>n.type==="input"&&n.props.type==="search").props.onChange({target:{value:"Python"}});tree=h.render();
 h.button(tree,"已回复").props.onClick();tree=await h.settle();
 assert.deepEqual(h.queries.at(-1),{page:1,size:20,q:"Python",status:"replied",requirementId:"",verdict:""});
 assert.equal(h.button(tree,"已回复").props["aria-pressed"],true);
 h.button(tree,"缺少材料").props.onClick();tree=await h.settle();assert.equal(h.queries.at(-1).verdict,"gap");assert.equal(h.queries.at(-1).status,"replied");
 assert.ok(h.nodes(tree).some(n=>n.type==="button"&&n.props["aria-label"]==="移出对照：候选人a"));
 assert.equal(h.counts.open,0);assert.equal(h.counts.reply,0);
 h.button(tree,"重置").props.onClick();await h.settle();assert.deepEqual(h.queries.at(-1),{page:1,size:20,q:"",status:"",requirementId:"",verdict:""});
});

test("selected heatmap cell identifies both candidate and requirement after returning to the matrix",async()=>{
 const h=fixture();let tree=await h.settle();
 const cell=h.nodes(tree).find(n=>n.type==="button"&&n.props["aria-label"]==="候选人a · Python要求 · 仅简历声明");
 assert.ok(cell);await cell.props.onClick();tree=await h.settle();h.button(tree,"候选人").props.onClick();tree=h.render();
 const selected=h.nodes(tree).find(n=>n.type==="button"&&n.props["aria-label"]==="候选人a · Python要求 · 仅简历声明");
 assert.equal(selected.props["aria-pressed"],true);assert.match(selected.props.className,/ring-inset/);
 assert.equal(h.counts.reply,0);
});
