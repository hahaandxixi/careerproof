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
const { AppRouterContext } = require("next/dist/shared/lib/app-router-context.shared-runtime.js");
const item = (id, verdict = "gap", extra = {}) => ({ requirementId: id, requirementTitle: `要求${id}`, skill: id, weight: 3, verdict, confirmationStatus: "pending", explanation: `解释${id}`, evidenceLevelGap: `缺口${id}`, evidenceList: [], aiCitationIds: [], ...extra });
const advice = (value, extra = {}) => ({ requirementId: value.requirementId, requirementTitle: value.requirementTitle, skill: value.skill, weight: value.weight, currentLevel: null, source: "rules", action: value.evidenceLevelGap, evidenceGap: value.evidenceLevelGap, citationIds: [], ...extra });
const report = (items, actions = []) => ({ id: "saved-report", items, actionPlan: actions, materials: [] });
const count = (html, text) => html.split(text).length - 1;
const render = (value, role = "student") => renderToStaticMarkup(React.createElement(AppRouterContext.Provider, { value: { push() { throw new Error("render must not navigate"); } } },
  React.createElement(Workspace, { report: value }, value.items.map(entry => React.createElement("article", { id: `requirement-${entry.requirementId}`, key: entry.requirementId }, React.createElement(RequirementActionPanel, { report: value, item: entry, role }))))));

test("one integrated workspace keeps the complete saved items even when a plan is limited to three", () => {
 const items = Array.from({length: 6}, (_, i) => item(`gap${i}`));
 const value = report(items,items.slice(0,3).map(entry => advice(entry)));
 const before = JSON.stringify(value); const html = render(value);
 assert.equal(count(html,"岗位匹配与补证工作台"),1);
 for (const entry of items) assert.ok(html.includes(`href="#requirement-${entry.requirementId}"`));
 assert.equal(count(html, "完成后上传新版材料"), 6);
 assert.equal(count(html, "复制补证建议"), 6);
 assert.ok(!html.includes("展开完整补证计划"));
 assert.equal(JSON.stringify(value),before);
});

test("identical rules advice and gap appear once in the action panel", () => {
 const value = item("same"); const html=render(report([value],[advice(value)]));
 assert.equal(count(html,value.evidenceLevelGap),1);
 assert.ok(html.includes("本地规则提示")); assert.ok(html.includes("建议怎么补"));
});

test("valid AI advice uses the saved requirement and drops foreign or duplicate citations", () => {
 const entry=item("ai","partial",{aiStatus:"validated",aiSuggestion:"保存参数校验记录",aiInformationGap:"缺少失败结果",aiCitationIds:["R1-E1"],evidenceList:[{citationId:"R1-E1",contextComplete:true}]});
 const value={...report([entry],[advice(entry,{source:"ai_suggestion",action:entry.aiSuggestion,evidenceGap:entry.aiInformationGap,citationIds:["R1-E1","R1-E1","R2-E9"]})]),evidenceContextVersion:"source-context-v2"};
 const html=render(value);
 assert.ok(html.includes("AI 证据建议")); assert.ok(html.includes("保存参数校验记录")); assert.ok(html.includes("缺少失败结果"));
 assert.equal(count(html,'href="#citation-R1-E1"'),1); // the saved suggestion citation; source disclosure is owned by ReportDetail
 assert.ok(!html.includes("R2-E9"));
});

test("rejected, unvalidated, fallback and stale-context AI text never becomes action advice", () => {
 const entry=item("ai","gap",{aiStatus:"validated",aiSuggestion:"不应展示为有效的AI建议",aiInformationGap:"旧AI缺口",aiCitationIds:[]});
 for (const change of [{aiFallbackUsed:true},{evidenceContextVersion:"legacy"},{items:[{...entry,aiStatus:"rejected"}]},{items:[{...entry,confirmationStatus:"corrected"}]}]) {
  const value={...report([entry],[advice(entry,{source:"ai_suggestion",action:entry.aiSuggestion,evidenceGap:entry.aiInformationGap})]),evidenceContextVersion:"source-context-v2",...change};
  const html=render(value); assert.ok(!html.includes(entry.aiSuggestion)); assert.ok(!html.includes("旧AI缺口")); assert.ok(html.includes("暂无已保存的具体行动计划"));
 }
});

test("non-students retain explanation and advice without private student task controls", () => {
 const value=item("admin");
 for(const role of ["admin","enterprise",undefined]) {
  const html=render(report([value],[advice(value)]),role ?? "anonymous");
  assert.ok(html.includes("本地规则提示")); assert.ok(html.includes(value.explanation));
  assert.ok(!html.includes(">开始补证</button>")); assert.ok(!html.includes('id="growth-')); assert.ok(!html.includes('href="/growth"'));
 }
});

test("review-only and unsupported states do not invent implementation deficiencies", () => {
 for(const value of [item("review","supported",{confirmationStatus:"rejected"}),item("outside","unsupported")]) {
  const html=render(report([value]));
  assert.ok(html.includes("当前需核对")); assert.ok(html.includes("完成后上传新版材料"));
  assert.ok(!html.includes(">开始补证</button>")); assert.ok(html.includes("不能由此认定实现不存在"));
 }
});

test("partial support and gaps expose their existing plan and explicit task trigger", () => {
 for(const state of ["partial","gap","claimed_only"]) {
  const value=item(state,state); const html=render(report([value],[advice(value)]));
  assert.ok(html.includes("当前缺口")); assert.ok(html.includes("建议怎么补")); assert.ok(html.includes("完成后上传新版材料"));
  assert.ok(html.includes("不必创建补证记录"));
 }
});

test("supported requirements lead with conclusions and evidence; optional growth stays secondary", () => {
 const value=item("complete","supported"); const html=render(report([value],[advice(value)]));
 assert.ok(html.includes("当前材料支持")); assert.ok(html.includes("材料支持不等于运行成功"));
 assert.ok(html.includes("材料有更新？按需查看补证指导"));
 assert.ok(!html.includes("建议怎么补")); assert.ok(!html.includes(">开始补证</button>"));
 assert.ok(!html.includes('class="btn min-h-11'));
});

test("support survives incomplete context and its warning remains outside collapsed details", () => {
 const value=item("context","supported",{evidenceList:[{citationId:"C",contextComplete:false}]});
 const html=render(report([value]));
 assert.ok(html.includes("有证据支持")); assert.ok(html.includes("部分引用上下文不完整"));
 assert.ok(html.indexOf("部分引用上下文不完整") < html.indexOf("<details"));
});

test("missing plans and unrelated actions never manufacture suggestions or requirements", () => {
 const value=item("current"); const html=render(report([value],[advice(item("foreign"),{action:"外部报告的建议"})]));
 assert.ok(html.includes("暂无已保存的具体行动计划")); assert.ok(!html.includes("外部报告的建议"));
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
 assert.equal(JSON.stringify(r),before);
});

test("generic checking guidance is explicitly separate from saved advice and never invents Redis facts", () => {
 const entry=item("cache","gap",{requirementTitle:"使用 Redis 缓存并在写入后失效"});
 const r=report([entry],[advice(entry,{action:"核对候选与要求的对应关系，补充直接相关的材料。"})]);
 const before=JSON.stringify(r); const html=render(r);
 for(const text of ["通用核对步骤","检查已有实现","已有实现","尚未实现","提交新版材料","查看报告原始建议","已提交的材料只需定位"]) assert.ok(html.includes(text),text);
 assert.ok(html.includes(r.actionPlan[0].action));
 assert.ok(!html.includes("cache.py") && !html.includes("Redis 已实现"));
 assert.equal(JSON.stringify(r),before);
});

test("a saved structured plan takes priority over generic instructions", () => {
 const entry=item("plan","gap",{aiStatus:"validated",aiSuggestion:"核对接口",aiInformationGap:"待核对失败路径",aiCitationIds:[],aiTaskPlan:{deliverable:"接口验证材料",steps:["核对异常分支","核对事务回滚"],acceptanceChecks:["版本与引用对应"]}});
 const r={...report([entry],[advice(entry,{source:"ai_suggestion",action:"核对接口"})]),evidenceContextVersion:"source-context-v2"};
 const html=render(r);
 assert.ok(html.includes("建议提交的材料")); assert.ok(html.includes("核对事务回滚"));
 assert.ok(!html.includes("通用核对步骤"));
});

test("action panel has no duplicate evidence shortcut; the article owns the single source disclosure", () => {
 for(const verdict of ["gap","partial","supported","unsupported"]) {
  const html=render(report([item("source",verdict)]));
  assert.ok(!html.includes("核对判断依据与来源"));
  assert.ok(!html.includes("核对具体证据"));
 }
 const detail=readFileSync(path.join(SRC,"components/ReportDetail.tsx"),"utf8");
 assert.ok(detail.includes("查看判断依据与来源引用（"));
 assert.ok(!detail.includes("查看 {item.evidenceList.length} 条来源证据"));
});

test("guidance can be copied and used for a new upload without creating a task", () => {
 const entry=item("cache","gap"); const html=render(report([entry],[advice(entry)]));
 assert.ok(html.includes("复制补证建议"));
 assert.ok(html.includes("完成后上传新版材料"));
 assert.ok(html.includes("不必创建补证记录"));
 assert.ok(!html.includes("已有记录与自定义计划（可选）"));
 assert.ok(!html.includes("查看已有补证记录"));
 assert.ok(!html.includes('>开始补证</button>'));
});

test("copied guidance keeps saved sources and conditional instructions; rejected AI never enters the clipboard", async () => {
 const {followUpCopyText}=await import(pathToFileURL(path.join(SRC,"lib/report-follow-up.ts")).href);
 const entry=item("cache","gap",{requirementTitle:"缓存失效要求",aiStatus:"rejected",aiSuggestion:"未经采用的旧建议"});
 const r={...report([entry],[advice(entry,{source:"ai_suggestion",action:entry.aiSuggestion})]),jobTitle:"后端岗位"};
 const text=followUpCopyText(r,entry);
 for(const value of ["后端岗位","缓存失效要求",entry.evidenceLevelGap,"通用核对步骤","未检索到引用不代表没有实现","旧报告和企业投递快照"]) assert.ok(text.includes(value),value);
 assert.ok(!text.includes(entry.aiSuggestion));
 assert.ok(!text.includes("已成功运行"));
});

test("legacy growth anchors resolve to current copy/upload guidance without reopening task creation",()=>{
 for(const verdict of ["gap","supported"]){
  const html=render(report([item("legacy",verdict)]));
  assert.equal(count(html,'id="growth-legacy"'),1);
  assert.ok(html.includes("复制补证建议")&&html.includes("完成后上传新版材料"));
  assert.ok(!html.includes("自定义补证计划")&&!html.includes("查看已有补证记录"));
 }
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
