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
const knownDim = (id,verdict,score) => ({...dim(id,verdict,score),formulaVersion:"evidence-v4"});

test("desktop radar stays visible without a collapsed overview control and retains raw scale",()=>{
 const html=render({dimensions:[dim("FastAPI long requirement","supported",65),dim("SQL","partial",40),dim("pytest","gap",0)]});
 assert.ok(html.includes("<svg"));assert.ok(!html.includes("hidden xl:block"));assert.ok(!html.includes("展开整体雷达"));
 assert.ok(html.includes("<title>FastAPI long requirement</title>"));
 assert.ok(html.includes(">100</text>"));assert.ok(!html.includes("65%"));
});
test("axis labels distinguish missing evidence from a scored zero without changing stored values",()=>{
 const html=render({dimensions:[dim("材料缺口","gap",0),dim("可评零值","supported",0),dim("规则未覆盖","unsupported",null)]});
 assert.ok(html.includes('aria-label="材料缺口，材料待补充，查看证据"'));
 assert.ok(!html.includes('0 · 材料待补充'));
 assert.ok(html.includes('aria-label="可评零值，有证据支持，0，查看证据"'));
 assert.ok(html.includes('0 · 有证据支持'));
 assert.ok(html.includes('aria-label="规则未覆盖，规则暂未支持，查看证据"'));
});

test("known whole-chart index changes geometry and readable values together; selection does not rescale axes",()=>{
 const dimensions=[knownDim("FastAPI","supported",65),knownDim("SQL","partial",40),knownDim("pytest","claimed_only",10)];
 const before=JSON.stringify(dimensions);
 const first=render({dimensions,initialRequirementId:"FastAPI"}), second=render({dimensions,initialRequirementId:"SQL"});
 for(const html of [first,second]){
   assert.match(html,/材料支持度指数 100/);assert.match(html,/61.5 · 部分证据支持/);assert.match(html,/15.4 · 仅简历声明/);
   assert.match(html,/原始分值/);assert.match(html,/evidence-v4/);assert.doesNotMatch(html,/65%|100%/);
 }
 // Same plotted coordinates after selecting another requirement; highlight/radius can differ.
 const points=html=>[...html.matchAll(/<circle cx="([^"]+)" cy="([^"]+)" r="[57]"/g)].map(m=>[Number(m[1]),Number(m[2])]);
 assert.deepEqual(points(first),points(second));assert.equal(points(first).length,3);
 assert.ok(Math.abs(Math.hypot(points(first)[0][0]-200,points(first)[0][1]-200)-108)<1e-10);
 assert.ok(Math.abs(Math.hypot(points(first)[1][0]-200,points(first)[1][1]-200)-108*40/65)<1e-10);
 assert.equal(JSON.stringify(dimensions),before);
});
test("unknown versions keep a whole raw chart; anomalous known raw values remain visible without a dot",()=>{
 const dimensions=[knownDim("FastAPI","supported",65),{...knownDim("SQL","partial",40),formulaVersion:"unknown"},knownDim("pytest","gap",0)];
 const html=render({dimensions});assert.match(html,/未换算/);assert.match(html,/65 · 有证据支持/);assert.match(html,/40 · 部分证据支持/);
 const bad=render({dimensions:[knownDim("FastAPI","supported",66),knownDim("SQL","partial",40),knownDim("pytest","gap",0)]});
 assert.match(bad,/超过已确认规则上限65/);assert.match(bad,/原始值 66/);
 assert.doesNotMatch(bad,/<title>FastAPI：材料支持度指数/);
});

test("actual requirement buttons and keyboard axes change the selected evidence without changing index coordinates",async()=>{
 const lib=await import("../src/lib/skill-radar.ts"), support=await import("../src/lib/support-index.js"), citations=await import("../src/lib/report-citations.ts");
 const cells=[];let cursor=0;
 const hooks={useId:()=>"radar-detail",useState(value){const i=cursor++;if(!(i in cells))cells[i]=value;return[cells[i],v=>{cells[i]=v;}];}};
 const stub=()=>null;
 const modules={react:hooks,"react/jsx-runtime":require("react/jsx-runtime"),"./EvidenceSnippet":{default:stub,__esModule:true},"./SourceIdentity":{default:stub,SourceIdentityDetails:stub,__esModule:true},"./SupportMeasureDetails":{default:stub,__esModule:true},"@/lib/skill-radar":lib,"@/lib/evidence-display":{evidenceLevelName:String},"@/lib/support-index.js":support,"@/lib/report-citations":citations};
 const code=transform(readFileSync(path.join(SRC,"components/SkillRadar.tsx"),"utf8"),{transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code;
 const mod={exports:{}};new Function("require","module","exports",code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
 const nodes=n=>!n||typeof n!=="object"?[]:[n,...React.Children.toArray(n.props?.children).flatMap(nodes)];
 const dimensions=[knownDim("FastAPI","supported",65),knownDim("SQL","partial",40),knownDim("pytest","gap",0)],changes=[];
 const items=dimensions.map(d=>({requirementId:d.requirementId,explanation:`source-for-${d.requirementId}`,evidenceList:[]}));
 const redraw=()=>{cursor=0;return mod.exports.default({dimensions,items,onRequirementChange:id=>changes.push(id)});};
 let tree=redraw();const points=tree=>nodes(tree).filter(n=>n.type==="circle"&&[5,7].includes(n.props.r)).map(n=>[n.props.cx,n.props.cy]);const initial=points(tree);
 nodes(tree).find(n=>n.type==="button"&&n.props["aria-pressed"]===false).props.onClick();tree=redraw();
 assert.ok(nodes(tree).some(n=>n.type==="p"&&n.props.children==="source-for-SQL"));assert.deepEqual(points(tree),initial);
 const axis=nodes(tree).find(n=>n.type==="g"&&n.props["aria-label"]?.startsWith("pytest，"));let prevented=false;
 axis.props.onKeyDown({key:"Enter",preventDefault(){prevented=true;}});tree=redraw();
 assert.equal(prevented,true);assert.deepEqual(changes,["SQL","pytest"]);assert.deepEqual(points(tree),initial);
 assert.ok(nodes(tree).some(n=>n.type==="p"&&n.props.children==="source-for-pytest"));
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
