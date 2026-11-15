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
const { renderToStaticMarkup } = require("react-dom/server");

const { default: Workspace, RequirementActionPanel } = await import(pathToFileURL(path.join(SRC, "components/ReportEvidenceWorkspace.tsx")).href);
const { RequirementSupplementTarget } = await import(pathToFileURL(path.join(SRC, "components/RequirementSupplement.tsx")).href);
const { default: CareerSupplementRoute } = await import(pathToFileURL(path.join(SRC, "components/CareerSupplementRoute.tsx")).href);
const {default: SourcePanel}=await import("../src/components/ReportSourcePanel.tsx");
const {default: AiExplanation}=await import("../src/components/ReportAiExplanation.tsx");
const { AppRouterContext } = require("next/dist/shared/lib/app-router-context.shared-runtime.js");
const item = (id, verdict = "gap", extra = {}) => ({ requirementId: id, requirementTitle: `要求${id}`, skill: id, weight: 3, verdict, confirmationStatus: "pending", explanation: `解释${id}`, evidenceLevelGap: `缺口${id}`, evidenceList: [], aiCitationIds: [], ...extra, evidenceList: (extra.evidenceList ?? []).map(source => ({filePath:"app.py",lineStart:1,lineEnd:2,snippet:"return saved", ...source})) });
const advice = (value, extra = {}) => ({ requirementId: value.requirementId, requirementTitle: value.requirementTitle, skill: value.skill, weight: value.weight, currentLevel: null, source: "rules", action: value.evidenceLevelGap, evidenceGap: value.evidenceLevelGap, citationIds: [], ...extra });
const report = (items, actions = []) => ({ id: "saved-report", items, actionPlan: actions, materials: [] });

test("career supplement keeps saved details and valid citations after showing the gap", () => {
 const input = {keyGap:"缺少查询",nextTask:"整理结果",reason:"需要核对",citationIds:["one","missing","one"],taskPlan:{deliverable:"查询脚本",acceptanceChecks:["检查条件","核对结果"],steps:["编写查询","保存输出"]}};
 const job = {assessedCount:1,evidence:[{citationId:"one",skill:"SQL",filePath:"src/app.py",lineStart:2,lineEnd:4}]};
 const html = renderToStaticMarkup(React.createElement(CareerSupplementRoute,{advice:input,job,planId:"saved-plan"}));
 for (const text of ["缺少查询","整理结果","需要核对","查询脚本","检查条件","核对结果","编写查询","保存输出","plan-citation-one"]) assert.ok(html.includes(text),text);
 assert.equal((html.match(/plan-citation-one/g)??[]).length,1);
 assert.ok(html.includes("returnPlan=saved-plan#plan-citation-one"));
 assert.doesNotMatch(html,/plan-citation-missing/);
 assert.match(html,/<details>/);
 for (const text of ["查询脚本","检查条件","编写查询"]) assert.ok(html.indexOf(text) < html.indexOf("<details"), text);
 const repeated = {...input,taskPlan:{...input.taskPlan,acceptanceChecks:["同一内容","同一内容"],steps:["同一步","同一步"]}};
 const saved = renderToStaticMarkup(React.createElement(CareerSupplementRoute,{advice:repeated,job,planId:"saved-plan"}));
 assert.equal((saved.match(/同一内容/g)??[]).length,2);
 assert.equal((saved.match(/同一步/g)??[]).length,2);
});
test("career citation uses a report anchor only for one matching saved source", () => {
 const evidence = {citationId:"plan-one",skill:"SQL",filePath:"query.sql",projectVersionId:"v1",projectFileId:"f1",lineStart:1,lineEnd:2};
 const job={assessedCount:1,evidence:[evidence]};
 const input={keyGap:"缺少输出",citationIds:["plan-one"]};
 const source={...evidence,citationId:"report-one"};
 const renderRoute=items=>renderToStaticMarkup(React.createElement(CareerSupplementRoute,{advice:input,job,planId:"saved-plan",report:{items}}));
 const a=item("a","supported",{evidenceList:[source]});
 assert.match(renderRoute([a]), /href="#citation-report-one"/);
 const b=item("b","supported",{evidenceList:[{...source,citationId:"report-two"}]});
 assert.match(renderRoute([a,b]), /returnPlan=saved-plan#plan-citation-plan-one/);
 assert.doesNotMatch(renderRoute([a,b]), /href="#citation-report-/);
});
const count = (html, text) => html.split(text).length - 1;
const render = (value, role = "student") => renderToStaticMarkup(React.createElement(AppRouterContext.Provider, { value: { push() { throw new Error("render must not navigate"); } } },
  React.createElement(Workspace, { report: value }, value.items.map(entry => React.createElement("article", { id: `requirement-${entry.requirementId}`, key: entry.requirementId },
    React.createElement(RequirementActionPanel, { report: value, item: entry, role }),
    role === "student" && (["gap", "partial", "claimed_only"].includes(entry.verdict) || entry.confirmationStatus === "rejected") ? React.createElement(RequirementSupplementTarget, { report: value, item: entry }) : null)))));

test("job-level advice keeps a separate copy action, even without a structured plan", () => {
 const entry=item("SQL");
 const r=report([entry]);
 const job={jobId:"job",jobTitle:"数据岗位",assessedCount:1,evidence:[]};
 const html=renderToStaticMarkup(React.createElement(CareerSupplementRoute,{
   advice:{keyGap:"核对 SQL 输出",nextTask:"保存执行结果",citationIds:[]},
   job,planId:"saved-plan",report:r,
 }));
 assert.match(html,/职业规划建议.*复制规划建议/);
 assert.doesNotMatch(html,/复制补证建议|sourceRequirement/);
 assert.doesNotMatch(render(r),/复制补证建议/);
});

test("explanation only omits the repeated chip for an already open readable sole citation", () => {
 const source={citationId:"R1-E1",projectVersionId:"v1",projectFileId:"f1",filePath:"app.py",lineStart:3,lineEnd:4,snippet:"actual line"};
 const entry=item("linked","supported",{aiStatus:"validated",aiExplanation:"可核对实现",aiCitationIds:["R1-E1"],evidenceList:[source]});
 const r={...report([entry]),analysisMode:"ai_evidence",materials:[{kind:"project",id:"v1",title:"项目",versionNumber:1}]};
 const explanation=value=>renderToStaticMarkup(React.createElement(AiExplanation,{report:r,item:value}));
 assert.doesNotMatch(explanation(entry),/其他解释来源/);
 assert.match(explanation({...entry,aiExplanation:"可核对实现 R1-E1"}),/href="#citation-R1-E1"/);
 assert.match(explanation({...entry,evidenceList:[{...source,snippet:""}]}),/href="#citation-R1-E1"/);
 assert.match(explanation({...entry,evidenceList:[{...source,citationId:null,projectFileId:"f2"},source]}),/href="#citation-R1-E1"/);
 const panel=renderToStaticMarkup(React.createElement(SourcePanel,{report:r,item:{...entry,evidenceList:[{...source,citationId:null,projectFileId:"f2"},source]}}));
 assert.match(panel,/id="citation-R1-E1" aria-label=/);
 assert.match(panel,/id="rule-source-linked-1" hidden=""/);
});

test("student requirement area leaves guidance to the supplement section", () => {
 const value = item("linked");
 const reportValue = report([value], [advice(value)]);
 const region = renderToStaticMarkup(React.createElement(RequirementActionPanel, { report: reportValue, item: value, role: "student" }));
 assert.doesNotMatch(region, /查看补证建议|href="#supplement-linked"/);
 assert.doesNotMatch(region, /复制补证建议|上传新版材料|本项已保存的具体要求|通用核对步骤/);
 const full = render(reportValue);
 assert.ok(full.includes('id="supplement-linked"'));
 assert.ok(!full.includes("本项补证与岗位对照中的当前要求一致"));
 assert.ok(!full.includes("本项已保存的具体要求"));
 assert.ok(!full.includes("复制补证建议"), "a repeated gap is not separate copyable advice");
 assert.ok(full.includes("添加项目材料"));
});
test("rule citations stay in the reader with alternatives available through existing anchors", () => {
 const first={citationId:null,projectVersionId:"v1",filePath:"src/app.py",snippet:"first implementation"};
 const r={...report([]),materials:[{kind:"project",id:"v1",title:"项目",versionNumber:1}]};
 const view=(sources,reader=true)=>{
  const entry=item("rules","supported",{evidenceList:sources});
  const sourcePanel=reader ? React.createElement(SourcePanel,{report:r,item:entry}) : undefined;
  return renderToStaticMarkup(React.createElement(RequirementActionPanel,{report:r,item:entry,sourcePanel}));
 };
 const single=view([first]);
 assert.doesNotMatch(single,/class="report-citation-chip"/);
 assert.match(single,/id="rule-source-rules-1"/);
 assert.doesNotMatch(view([first],false),/href="#rule-source-rules-1"/);
 const unreadable=view([{...first,snippet:""}]);
 assert.match(unreadable,/id="rule-source-rules-1"/);
 assert.match(unreadable,/来源暂不可读/);
 const two=view([first,{...first,filePath:"tests/app.py",lineStart:5,lineEnd:7}]);
 assert.match(two,/id="rule-source-rules-1"/);
 assert.doesNotMatch(two,/href="#rule-source-rules-1"/);
 assert.match(two,/href="#rule-source-rules-2"/);
});

test("one integrated workspace keeps the complete saved items even when a plan is limited to three", () => {
 const items = Array.from({length: 6}, (_, i) => item(`gap${i}`));
 const value = report(items,items.slice(0,3).map(entry => advice(entry,{action:`核对保存文件和对应行号：${entry.skill}`})));
 const before = JSON.stringify(value); const html = render(value);
 assert.equal(count(html,'aria-label="岗位要求与证据"'),1);
 for (const entry of items) assert.ok(html.includes(`href="#requirement-${entry.requirementId}"`));
 assert.equal(count(html, "添加项目材料"), 6);
 assert.equal(count(html, "复制补证建议"), 3);
 assert.ok(!html.includes("展开完整补证计划"));
 assert.equal(JSON.stringify(value),before);
});

test("identical rules advice and gap appear once in the action panel", () => {
 const value = item("same"); const html=render(report([value],[advice(value)]));
 assert.equal(count(html,value.evidenceLevelGap),1);
 assert.ok(!html.includes("本地规则提示")); assert.ok(!html.includes("本项已保存的具体要求"));
});

test("valid AI advice uses the saved requirement without adding citation shortcuts in the action panel", () => {
 const entry=item("ai","partial",{aiStatus:"validated",aiSuggestion:"保存参数校验记录",aiInformationGap:"缺少失败结果",aiCitationIds:["R1-E1"],evidenceList:[{citationId:"R1-E1",contextComplete:true}]});
 const value={...report([entry],[advice(entry,{source:"ai_suggestion",action:entry.aiSuggestion,evidenceGap:entry.aiInformationGap,citationIds:["R1-E1","R1-E1","R2-E9"]})]),evidenceContextVersion:"source-context-v2"};
 const html=render(value);
 assert.ok(html.includes("AI 证据建议")); assert.ok(html.includes("保存参数校验记录")); assert.ok(html.includes("缺少失败结果"));
 assert.doesNotMatch(html,/href="#citation-R1-E1"/);
 assert.ok(!html.includes("R2-E9"));
});

test("rejected, unvalidated, fallback and stale-context AI text never becomes action advice", () => {
 const entry=item("ai","gap",{aiStatus:"validated",aiSuggestion:"不应展示为有效的AI建议",aiInformationGap:"旧AI缺口",aiCitationIds:[]});
 for (const change of [{aiFallbackUsed:true},{evidenceContextVersion:"legacy"},{items:[{...entry,aiStatus:"rejected"}]},{items:[{...entry,confirmationStatus:"corrected"}]}]) {
  const value={...report([entry],[advice(entry,{source:"ai_suggestion",action:entry.aiSuggestion,evidenceGap:entry.aiInformationGap})]),evidenceContextVersion:"source-context-v2",...change};
  const html=render(value); assert.ok(!html.includes(entry.aiSuggestion)); assert.ok(!html.includes("旧AI缺口")); assert.ok(!html.includes("本项已保存的具体要求")); assert.ok(!html.includes("通用核对步骤与材料清单"));
 }
});

test("non-students retain explanation and advice without private student task controls", () => {
 const value=item("admin");
 for(const role of ["admin","enterprise",undefined]) {
  const html=render(report([value],[advice(value)]),role ?? "anonymous");
  assert.ok(!html.includes("本地规则提示")); assert.ok(html.includes(value.evidenceLevelGap));
  assert.ok(!html.includes(">开始补证</button>")); assert.ok(!html.includes('id="growth-')); assert.ok(!html.includes('href="/growth"'));
 }
});

test("review-only keeps review guidance while unsupported keeps its rule gap without upload advice", () => {
 const review=render(report([item("review","supported",{confirmationStatus:"rejected"})]));
 assert.ok(review.includes("当前需核对")); assert.ok(review.includes("添加项目材料"));
 assert.ok(!review.includes(">开始补证</button>")); assert.ok(!review.includes("通用核对步骤与材料清单"));
 const unsupported=render(report([item("outside","unsupported")]));
 assert.ok(unsupported.includes("规则暂未支持")); assert.ok(unsupported.includes("请人工核对岗位要求和已保存材料"));
 assert.ok(!unsupported.includes("添加项目材料")); assert.ok(!unsupported.includes("上传即可解决"));
 assert.ok(!unsupported.includes("查看补证建议")); assert.ok(!unsupported.includes('href="/portfolio"'));
});

test("partial support and gaps expose their existing plan and explicit task trigger", () => {
 for(const state of ["partial","gap","claimed_only"]) {
  const value=item(state,state); const html=render(report([value],[advice(value)]));
  assert.ok(html.includes("当前缺口")); assert.ok(html.includes(value.evidenceLevelGap)); assert.ok(!html.includes("本项已保存的具体要求")); assert.ok(html.includes("添加项目材料"));
  assert.ok(html.includes('href="/portfolio"'), "upload remains navigation without task creation or analysis");
 }
});

test("supported requirements lead with conclusions and evidence; optional growth stays secondary", () => {
 const value=item("complete","supported"); const html=render(report([value],[advice(value)]));
 assert.ok(html.includes("判断依据")); assert.ok(!html.includes("材料支持不等于运行成功"));
 assert.ok(!html.includes("材料有更新？按需查看补证指导"));
 assert.ok(!html.includes("本项已保存的具体要求")); assert.ok(!html.includes(">开始补证</button>"));
 assert.ok(!html.includes('class="btn min-h-11'));
});

test("support survives incomplete context without duplicating the source pane's warning in actions", () => {
 const value=item("context","supported",{evidenceList:[{citationId:"C",contextComplete:false}]});
 const html=render(report([value]));
 assert.ok(html.includes("有证据支持")); assert.ok(!html.includes("部分引用上下文不完整"));
 assert.equal(value.evidenceList[0].contextComplete,false);
});

test("missing plans and unrelated actions never manufacture suggestions or requirements", () => {
 const value=item("current"); const html=render(report([value],[advice(item("foreign"),{action:"外部报告的建议"})]));
 assert.ok(!html.includes("本项已保存的具体要求")); assert.ok(!html.includes("通用核对步骤与材料清单")); assert.ok(!html.includes("外部报告的建议"));
 assert.ok(!html.includes('href="#requirement-foreign"'));
});

test("empty report does not masquerade as full support", () => {
 const html=render(report([])); assert.ok(html.includes("本报告尚无逐项要求"));
 assert.ok(!html.includes(">开始补证</button>")); assert.ok(!html.includes('href="#requirement-'));
});

test("saved structured plans retain deliverable, steps and checks without changing the snapshot", () => {
 const value=item("structured","partial",{aiStatus:"validated",aiSuggestion:"核对提交的接口材料",aiInformationGap:"缺少异常输出",aiCitationIds:["A"],evidenceList:[{citationId:"A"}],aiTaskPlan:{deliverable:"接口验证记录",steps:["运行失败场景"],acceptanceChecks:["记录响应码与源码版本"]}});
 const r={...report([value],[advice(value,{source:"ai_suggestion",action:value.aiSuggestion})]),evidenceContextVersion:"source-context-v2"};
 const before=JSON.stringify(r); const html=render(r);
 for(const t of ["接口验证记录","运行失败场景","记录响应码与源码版本"]) assert.ok(html.includes(t));
 const order=["提交什么","执行步骤","核对项"].map(label=>html.indexOf(label));
 assert.ok(order[0]>=0 && order[0]<order[1] && order[1]<order[2]);
 assert.equal(JSON.stringify(r),before);
});

test("saved advice remains without generic steps or invented Redis facts", () => {
 const entry=item("cache","gap",{requirementTitle:"使用 Redis 缓存并在写入后失效"});
 const r=report([entry],[advice(entry,{action:"核对候选与要求的对应关系，补充直接相关的材料。"})]);
 const before=JSON.stringify(r); const html=render(r);
 for(const text of ["通用核对步骤","检查已有实现","尚未实现","建议提交的材料"]) assert.ok(!html.includes(text),text);
 assert.equal(count(html, r.actionPlan[0].action),1);
 assert.ok(!html.includes("cache.py") && !html.includes("Redis 已实现"));
 assert.equal(JSON.stringify(r),before);
});

test("a saved structured plan takes priority over generic instructions", () => {
 const entry=item("plan","gap",{aiStatus:"validated",aiSuggestion:"核对接口",aiInformationGap:"待核对失败路径",aiCitationIds:[],aiTaskPlan:{deliverable:"接口验证材料",steps:["核对异常分支","核对事务回滚"],acceptanceChecks:["版本与引用对应"]}});
 const r={...report([entry],[advice(entry,{source:"ai_suggestion",action:"核对接口"})]),evidenceContextVersion:"source-context-v2"};
 const html=render(r);
 assert.ok(html.includes("接口验证材料")); assert.ok(html.includes("核对事务回滚"));
 assert.ok(!html.includes("通用核对步骤"));
});

test("a validated structured plan without an actionPlan entry never claims that no concrete plan exists", () => {
 const entry=item("plan-only","gap",{aiStatus:"validated",aiSuggestion:"核对接口",aiInformationGap:"缺少异常记录",aiCitationIds:[],aiTaskPlan:{deliverable:"验证记录",steps:["运行异常请求"],acceptanceChecks:["注明固定源码版本"]}});
 const value={...report([entry]),evidenceContextVersion:"source-context-v2"};
 const before=JSON.stringify(value); const html=render(value);
 assert.ok(html.includes("运行异常请求") && html.includes("验证记录") && html.includes("注明固定源码版本"));
 assert.ok(!html.includes("通用核对步骤与材料清单"));
 assert.equal(JSON.stringify(value),before);
});

test("action panel has no duplicate evidence shortcut; the article owns a single linked source reader", () => {
 for(const verdict of ["gap","partial","supported","unsupported"]) {
  const html=render(report([item("source",verdict)]));
  assert.ok(!html.includes("核对判断依据与来源"));
  assert.ok(!html.includes("核对具体证据"));
 }
 const detail=readFileSync(path.join(SRC,"components/ReportDetail.tsx"),"utf8");
 assert.equal(count(detail,"<ReportSourcePanel "),1);
 assert.ok(!detail.includes("查看 {item.evidenceList.length} 条来源证据"));
 const entry=item("source","supported",{evidenceList:[{citationId:"S1",filePath:"app.py",lineStart:4,lineEnd:5,snippet:"saved-source",contextComplete:true}]});
 const html=renderToStaticMarkup(React.createElement(SourcePanel,{report:report([entry]),item:entry}));
 assert.equal(count(html,'aria-label="source的证据来源"'),1);
 assert.ok(html.includes('id="citation-S1"')&&html.includes("saved-source"));
 assert.doesNotMatch(html,/引用原文|其他来源/);
});

test("the generic current-gap notice and duplicate citation chips stay out of the requirement workspace", () => {
 const gap = "核对候选与要求的对应关系，补充直接相关的材料或经校验的 AI 引用解释。";
 const entry = item("source", "gap", { evidenceLevelGap: gap, evidenceList: [{ citationId: "S1", filePath: "README.md", lineStart: 1, lineEnd: 3, snippet: "saved-source", contextComplete: true }] });
 const value = report([entry]);
 const html = renderToStaticMarkup(React.createElement(RequirementActionPanel, { report: value, item: entry, sourcePanel: React.createElement(SourcePanel, { report: value, item: entry }) }));
 assert.doesNotMatch(html, /当前缺口|核对候选与要求|本项引用/);
 assert.match(html, /saved-source/);
});

test("guidance can be copied and used for a new upload without creating a task", () => {
 const entry=item("cache","gap"); const html=render(report([entry],[advice(entry,{action:"补充缓存失效实现的位置"})]));
 assert.ok(html.includes("复制补证建议"));
 assert.ok(html.includes("添加项目材料"));
 assert.ok(html.includes('href="/portfolio"'), "upload remains navigation without task creation or analysis");
 assert.ok(!html.includes("已有记录与自定义计划（可选）"));
 assert.ok(!html.includes("查看已有补证记录"));
 assert.ok(!html.includes('>开始补证</button>'));
});

test("copying uses the displayed report plan and verified display title, never rejected AI", async () => {
 const {followUpCopyText}=await import(pathToFileURL(path.join(SRC,"lib/report-follow-up.ts")).href);
 const plan={deliverable:"接口核对记录",steps:["打开接口文件","核对校验","注明运行环境"],acceptanceChecks:["记录版本","保留错误输出"]};
 const entry=item("cache","gap",{requirementTitle:"缓存失效要求",aiStatus:"validated",aiTaskPlan:plan,aiSuggestion:"记录失效时机"});
 const r={...report([entry],[advice(entry,{source:"rules",action:"核对失效位置"})]),evidenceContextVersion:"source-context-v2",jobId:"6c8ad563-ebf8-427c-b4a3-82905f37dbd0",jobTitle:"数据工程实习生 · 本地合成验收"};
 const copied=followUpCopyText(r,entry);
 for(const value of ["岗位：数据工程实习生","缓存失效要求",entry.evidenceLevelGap,"核对失效位置",plan.deliverable,...plan.steps,...plan.acceptanceChecks,"旧报告和企业投递快照"]) assert.ok(copied.includes(value),value);
 assert.doesNotMatch(copied,/本地合成验收|建议（）：|已成功运行/);
 const rejected={...entry,aiStatus:"rejected"};
 assert.equal(followUpCopyText({...r,actionPlan:[advice(rejected,{source:"ai_suggestion",action:entry.aiSuggestion})]},rejected),null);
});

test("legacy growth anchors lead to the supplement section",()=>{
 const html=render(report([item("legacy","gap")]));
 assert.equal(count(html,'id="growth-legacy"'),1);
 assert.ok(!html.includes("复制补证建议")&&html.includes("添加项目材料"));
 const source=readFileSync(path.join(SRC,"components/ReportDetail.tsx"),"utf8");
 assert.ok(source.indexOf("id={`growth-${item.requirementId}`}") > source.indexOf('id: "report-supplement"'));
 assert.ok(!html.includes("自定义补证计划")&&!html.includes("查看已有补证记录"));
});

test("no report requirement mounts task lookup or task plan editing for any saved evidence state",()=>{
 for(const verdict of ["gap","partial","claimed_only","supported","unsupported"]){
  const html=render(report([item("no-task",verdict)]));
  assert.ok(!html.includes("查看已有补证记录"));
  assert.ok(!html.includes("确认记录这条建议"));
  assert.ok(!html.includes("保存并进入补证"));
  assert.ok(!html.includes("<form"));
 }
 const source=readFileSync(path.join(SRC,"components/ReportEvidenceWorkspace.tsx"),"utf8");
 assert.ok(!source.includes("GrowthTaskStart"));
 assert.ok(!source.includes("existingGrowthTask"));
});

test("mixed citations retain their original source slots and only student material actions are enabled", () => {
 const source = {projectVersionId:"v1",projectFileId:"f1",filePath:"app.py",snippet:"saved line",contextComplete:true};
 const entry = item("mixed","supported",{aiCitationIds:["AI-1"],evidenceList:[
   {...source,citationId:"AI-1",lineStart:1,lineEnd:2},
   {...source,citationId:null,lineStart:5,lineEnd:6},
   {...source,citationId:null,lineStart:9,lineEnd:10},
 ]});
 const r = {...report([entry]),id:"report-1",materials:[{kind:"project",id:"v1",title:"项目",versionNumber:1}]};
 const action=renderToStaticMarkup(React.createElement(RequirementActionPanel,{report:r,item:entry,role:"student",explanationVisible:true}));
 const readonly=renderToStaticMarkup(React.createElement(SourcePanel,{report:r,item:entry}));
 const student=renderToStaticMarkup(React.createElement(SourcePanel,{report:r,item:entry,canOpenMaterial:true}));
 for(const slot of [2,3]){
  assert.ok(!action.includes(`href="#rule-source-mixed-${slot}"`));
  assert.ok(readonly.includes(`href="#rule-source-mixed-${slot}"`));
  assert.ok(readonly.includes(`id="rule-source-mixed-${slot}"`));
  assert.ok(student.includes(`sourceId=rule-source-mixed-${slot}`));
 }
 assert.ok(!action.includes('href="#rule-source-mixed-1"'));
 assert.ok(!readonly.includes('href="/materials/'));
 assert.ok(readonly.includes("saved line"));
});
