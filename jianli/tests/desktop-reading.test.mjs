import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
const require=createRequire(import.meta.url),React=require("react"),{transform}=require("sucrase");
function load(file,modules){const mod={exports:{}};new Function("require","module","exports",transform(readFileSync(new URL(`../src/components/${file}.tsx`,import.meta.url),"utf8"),{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);return mod.exports.default;}
const nodes=n=>!n||typeof n!=="object"?[]:[n,...React.Children.toArray(n.props?.children).flatMap(nodes)];
const text=n=>typeof n==="string"||typeof n==="number"?String(n):React.Children.toArray(n?.props?.children).map(text).join("");
test("empty first page has no controls; an out-of-range empty page retains its recovery",()=>{
 const Pagination=load("ListPagination",{"react/jsx-runtime":require("react/jsx-runtime"),"@/lib/list-pagination.js":{pageBounds:v=>({previous:v.page>1,next:false}),paginationSummary:()=>"分页"}});
 assert.equal(Pagination({value:{total:0,page:1,pageSize:20},onPage(){}}),null);
 let page;const tree=Pagination({value:{total:0,page:3,pageSize:20},onPage:n=>page=n});nodes(tree).find(n=>n.type==="button").props.onClick();assert.equal(page,2);
});
test("wrapping and expanded reading preserve physical line numbers and copying returns only original bytes",async()=>{
 const cells=[];let cursor=0;const hooks={useState(value){const i=cursor++;if(!(i in cells))cells[i]=value;return[cells[i],v=>{cells[i]=typeof v==="function"?v(cells[i]):v;}];},useRef(value){const i=cursor++;return cells[i]??={current:value};}};
 const Snippet=load("EvidenceSnippet",{react:hooks,"react/jsx-runtime":require("react/jsx-runtime"),"@/lib/source-label":{sourceLabel:e=>e.filePath}});
 const evidence={filePath:"app.py",lineStart:20,lineEnd:21,snippet:"    "+"long_identifier".repeat(40)+"\n\treturn 1",contextComplete:true,contextNote:"完整原文"};const original=JSON.stringify(evidence);
 const render=()=>{cursor=0;return Snippet({evidence});};let tree=render();const button=label=>nodes(tree).find(n=>n.type==="button"&&text(n)===label);
 assert.match(nodes(tree).find(n=>n.type==="pre").props.className,/max-h-80/);
 button("换行").props.onClick();tree=render();assert.equal(button("换行").props["aria-pressed"],true);assert.ok(nodes(tree).some(n=>n.props?.className?.includes("whitespace-pre-wrap")));
 button("展开阅读").props.onClick();tree=render();assert.ok(!nodes(tree).find(n=>n.type==="pre").props.className.includes("max-h-80"));
 let focus=0;button("收起阅读").props.ref.current={focus(){focus++;}};button("收起并返回引用").props.onClick();tree=render();assert.equal(focus,1);
 const old=Object.getOwnPropertyDescriptor(globalThis,"navigator");let copied;
 try{Object.defineProperty(globalThis,"navigator",{configurable:true,value:{clipboard:{writeText:async value=>{copied=value;}}}});await button("复制原文").props.onClick();assert.equal(copied,evidence.snippet);}finally{if(old)Object.defineProperty(globalThis,"navigator",old);else delete globalThis.navigator;}
 const pre=nodes(tree).find(n=>n.type==="pre");assert.match(text(pre),/20/);assert.match(text(pre),/21/);assert.equal(JSON.stringify(evidence),original);assert.doesNotMatch(text(tree),/内容已截断/);
});
