// E2E-02-R1 回归：回复失败（请求失败/响应丢失）后草稿必须真实可编辑。
// 测试环境没有浏览器 DOM 且禁止安装依赖：这里用 sucrase 同步转译加载真实 .tsx 组件代码，
// 再用 react-dom/server 渲染真实元素并直接调用真实 onChange 管线——不匹配源码字符串。
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
const { default: SkillRadar } = await import(pathToFileURL(path.join(SRC, "components/SkillRadar.tsx")).href);
const dim = (id,verdict,score) => ({requirementId:id,title:id,skill:id,verdict,score,weight:1,evidenceLevel:null});
const render = props => renderToStaticMarkup(React.createElement(SkillRadar,props));

test("desktop radar stays visible without a collapsed overview control and retains raw scale",()=>{
 const html=render({dimensions:[dim("FastAPI long requirement","supported",65),dim("SQL","partial",40),dim("pytest","gap",0)]});
 assert.ok(html.includes("<svg"));assert.ok(!html.includes("hidden xl:block"));assert.ok(!html.includes("展开整体雷达"));
 assert.ok(html.includes("<title>FastAPI long requirement</title>"));
 assert.ok(html.includes(">100</text>"));assert.ok(!html.includes("65%"));
});
test("linked detail renders only selected requirement citations and keeps sources collapsed", () => {
 // 传智杯48：正常数据改为 evidence-v3 单项可达值 65/40/0（不再用 85/55 假装高分）
 const dimensions=[dim("Python","supported",65),dim("SQL","partial",40),dim("pytest","gap",0)];
 const items=[{requirementId:"Python",explanation:"Python依据",evidenceList:[{citationId:"R1-E1",filePath:"main.py",lineStart:1,lineEnd:3,snippet:"example-source-only",contextComplete:true}]}];
 const html=render({dimensions,items,initialRequirementId:"Python"});
 assert.ok(html.includes("R1-E1") && html.includes("example-source-only"));
 assert.ok(!/<details[^>]*\bopen[= >]/.test(html));
 const gap=render({dimensions,items,initialRequirementId:"pytest"});
 assert.ok(!gap.includes("R1-E1") && !gap.includes("example-source-only"));
 assert.ok(gap.includes("缺材料不代表没有能力"));
 assert.ok(!gap.includes("<polygon"));
});
test("synthetic radar never fabricates citations and supports fewer than three requirements", () => {
 const html=render({dimensions:[dim("SQL","unsupported",null)],synthetic:true});
 assert.ok(html.includes("没有真实来源文件"));
  assert.ok(html.includes("规则暂未支持") && !html.includes("<svg"));
 assert.ok(html.includes('aria-pressed="true"') && html.includes("选择岗位要求"));
});
test("reference source cannot be presented as personal contribution", () => {
 const html=render({dimensions:[dim("Python","supported",65)],items:[{requirementId:"Python",explanation:"已保存解释",evidenceList:[{citationId:"REF1",filePath:"tutorial.py",snippet:"reference-source",provenance:"reference",contextComplete:false,contextNote:"截取片段",lineStart:1,lineEnd:2}]}]});
 assert.ok(html.includes("参考材料，不能证明本人贡献"));
 assert.ok(html.includes("截取片段"));
});

for(const [aiStatus,fallback,adopted] of [["validated",false,true],["rejected",false,false],["invalid_citations",false,false],["validated",true,false]]) {
 test(`radar adopted interpretation ${aiStatus}/${fallback}`,()=>{
 const item={requirementId:"sql",aiStatus,explanation:"规则依据",aiExplanation:"MODEL-EXPLANATION",aiInformationGap:"MODEL-GAP",evidenceLevelGap:"规则缺口",evidenceList:[]};
 const html=render({dimensions:[dim("sql","supported",65)],items:[item],aiFallbackUsed:fallback});
 assert.equal(html.includes("MODEL-EXPLANATION"),adopted);assert.equal(html.includes("MODEL-GAP"),adopted);
 if(!adopted)assert.ok(html.includes("规则依据")&&html.includes("规则缺口"));
 });
}
