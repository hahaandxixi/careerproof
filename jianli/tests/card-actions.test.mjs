import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(here, "../src");
const require = createRequire(import.meta.url);
const { transform } = require("sucrase");

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("next/") && !specifier.endsWith(".js")) {
      try { return nextResolve(specifier + ".js", context); } catch {}
      return nextResolve(specifier, context);
    }
    if (specifier.startsWith("@/")) {
      const base = path.join(SRC, specifier.slice(2));
      for (const candidate of [base, base + ".ts", base + ".tsx", path.join(base, "index.ts"), path.join(base, "index.tsx")]) {
        try { return nextResolve(pathToFileURL(candidate).href, context); } catch {}
      }
      throw new Error(`无法解析别名导入：${specifier}`);
    }
    if ((specifier.startsWith("./") || specifier.startsWith("../")) && !path.extname(specifier)) {
      for (const suffix of ["", ".ts", ".tsx", "/index.ts", "/index.tsx", ".js", "/index.js"]) {
        try { return nextResolve(new URL(specifier + suffix, context.parentURL).href, context); } catch {}
      }
      return nextResolve(specifier, context);
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".json")) return { format: "module", source: `export default ${readFileSync(fileURLToPath(url), "utf8")}`, shortCircuit: true };
    if (url.endsWith(".ts") || url.endsWith(".tsx")) {
      const out = transform(readFileSync(fileURLToPath(url), "utf8"), {
        transforms: ["typescript", "jsx"], jsxRuntime: "automatic", production: false, filePath: url,
      });
      return { format: "module", source: out.code, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});

const React = require("react");
const { renderToStaticMarkup: render } = require("react-dom/server");
const { ManagedJobCard } = await import("../src/components/JobList.tsx");
const { NotificationCard } = await import("../src/components/NotificationCenter.tsx");
const { ApplicationEmptyState } = await import("../src/components/ApplicationBoard.tsx");
const { ReportHistoryCard } = await import("../src/components/ReportList.tsx");
const nodes=n=>!n||typeof n!=="object"?[]:[n,...React.Children.toArray(n.props?.children).flatMap(nodes)];
const text=n=>typeof n==="string"||typeof n==="number"?String(n):React.Children.toArray(n?.props?.children).map(text).join("");
const job={id:"job-a",title:"Python 后端",companyName:"公司",city:"杭州",employmentType:"internship",status:"published",description:"原岗位描述",category:"software",requirementCount:5,applicationCount:3,pendingApplicationCount:2};

test("managed job actions retain destinations, true counts and state outside the action group",()=>{
 const tree=ManagedJobCard({job,changing:"",onStatusChange(){}});
 const html=render(tree);
 assert.match(html,/投递 3 · 待回复 2/);assert.match(html,/已发布/);
 for(const href of ["/jobs/job-a","/jobs/job-a/edit","/jobs/job-a/applications"])assert.ok(html.includes(`href="${href}"`));
 assert.match(html,/<a class="btn-secondary" href="\/jobs\/job-a">查看岗位<\/a>/);
 assert.match(html,/关闭岗位/);assert.match(html,/card-actions\b/);
 const groups=nodes(tree).filter(n=>n.props?.className?.split(" ").includes("card-actions"));
 assert.equal(groups.length,1);
 assert.deepEqual(nodes(groups[0]).filter(n=>n.type==="button"||n.props?.href).map(text),["编辑岗位","查看投递","查看岗位","关闭岗位"]);
 assert.doesNotMatch(text(groups[0]),/已发布|投递 3 · 待回复 2/);
 const draft=render(React.createElement(ManagedJobCard,{job:{...job,status:"draft"},changing:"job-a",onStatusChange(){}}));
 assert.match(draft,/草稿/);assert.match(draft,/更新中…/);assert.match(draft,/<button[^>]*disabled/);assert.match(draft,/查看投递/);
});
test("closing needs confirmation, cancelling leaves data unchanged; publishing remains explicit",()=>{
 const original=JSON.stringify(job);const old=globalThis.window;const calls=[];
 try{
  globalThis.window={confirm:()=>false};
  let tree=ManagedJobCard({job,changing:"",onStatusChange:j=>calls.push(j.id)});
  nodes(tree).find(n=>n.type==="button").props.onClick();assert.deepEqual(calls,[]);
  globalThis.window.confirm=()=>true;nodes(tree).find(n=>n.type==="button").props.onClick();assert.deepEqual(calls,["job-a"]);
  globalThis.window.confirm=()=>{throw Error("publish does not use close confirmation");};
  tree=ManagedJobCard({job:{...job,status:"draft"},changing:"",onStatusChange:j=>calls.push(j.id)});
  assert.equal(text(nodes(tree).find(n=>n.type==="button")),"发布岗位");nodes(tree).find(n=>n.type==="button").props.onClick();
  assert.equal(calls.length,2);assert.equal(JSON.stringify(job),original);
 }finally{if(old===undefined)delete globalThis.window;else globalThis.window=old;}
});
test("notification short action delegates by id; unavailable and busy states remain guarded",()=>{
 const item={id:"notice-a",type:"replied",title:"企业已回复，请在投递详情核对正文",createdAt:"2026-10-29T12:00:00Z",readAt:null,accessible:true};
 const original=JSON.stringify(item),opened=[],read=[];
 const tree=NotificationCard({item,busy:false,onOpen:id=>opened.push(id),onRead:id=>read.push(id)});
 const html=render(tree);assert.match(html,/>企业已回复</);assert.doesNotMatch(html,/核对正文|核对授权并打开/);
 for(const button of nodes(tree).filter(n=>n.type==="button"))button.props.onClick();
 assert.deepEqual(opened,["notice-a"]);assert.deepEqual(read,["notice-a"]);assert.equal(JSON.stringify(item),original);
 const unavailable=NotificationCard({item:{...item,accessible:false,readAt:"saved"},busy:false,onOpen(){throw Error("unauthorized");},onRead(){}});
 assert.equal(nodes(unavailable).filter(n=>n.type==="button").length,0);assert.match(text(unavailable),/不可访问/);
 const busy=NotificationCard({item,busy:true,onOpen(){},onRead(){}});assert.ok(nodes(busy).filter(n=>n.type==="button").every(n=>n.props.disabled));
 const other=render(NotificationCard({item:{...item,type:"viewed",title:"已查看，不代表录用"},busy:false,onOpen(){},onRead(){}}));assert.match(other,/已查看，不代表录用/);
});
test("empty candidate list distinguishes an applied filter and offers only real recovery actions",()=>{
 let cleared=0;const filtered=ApplicationEmptyState({filtered:true,onClear:()=>cleared++});
 assert.match(text(filtered),/没有符合筛选的投递/);nodes(filtered).find(n=>n.type==="button").props.onClick();assert.equal(cleared,1);
 const empty=ApplicationEmptyState({filtered:false,onClear(){throw Error("no filter");}});
 assert.equal(nodes(empty).filter(n=>n.type==="button").length,0);assert.match(text(empty),/暂无投递/);
 assert.match(render(empty),/href="\/demo\/heatmap"/);assert.match(text(empty),/学生确认授权后/);
});
test("history action still filters the actual job and report links keep the fixed report id",()=>{
 let target;
 const report={id:"fixed-report",jobId:"fixed-job",jobTitle:"岗位",candidateName:"小江",createdAt:"2026-10-29T12:00:00Z",summary:"原摘要",jobReportCount:4};
 const tree=ReportHistoryCard({report,onSameJob:id=>target=id});
 nodes(tree).find(n=>n.type==="button"&&text(n)==="历史报告 · 4").props.onClick();
 assert.equal(target,"fixed-job");assert.match(render(tree),/href="\/reports\/fixed-report"/);assert.match(text(tree),/报告详情/);
});
