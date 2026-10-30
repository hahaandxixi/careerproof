// 传智杯44：我的投递卡片回归。突出岗位/公司/状态/回复/下一动作，事件默认折叠，
// 撤回二次确认与重新投递入口可用，查看/下载不得推断录用。
// 沿用 sucrase 转译加载真实 .tsx 的做法；卡片是无状态组件，可直接调用于交互验证。
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
const { renderToStaticMarkup: render } = require("react-dom/server");
const { ReportHistoryCard } = await import("../src/components/ReportList.tsx");
const { SelectedRequirementEvidence, toggleComparisonCandidate, RequirementFocusSelect, SavedRequirementDetail, FixedReportOverview } = await import("../src/components/ApplicationBoard.tsx");

test("fixed report overview separates evidence support, gaps and uncovered requirements without changing the snapshot", () => {
  const report = {
    id: "report-fixed", jobTitle: "后端岗位", createdAt: "2026-10-27T00:00:00Z",
    summary: "保留的完整判断", analysisMode: "rules", aiFallbackUsed: true,
    materials: [{ kind: "project", id: "version-a", title: "报名服务", versionNumber: 2 }],
    items: ["supported", "partial", "claimed_only", "gap", "unsupported"].map((verdict, index) => ({ requirementId: `r${index}`, verdict, weight: 1 })),
  };
  const original = JSON.stringify(report);
  const html = render(React.createElement(FixedReportOverview, { application: { candidateName: "合成甲", report } }));
  assert.match(html, /合成甲 · 投递时固定报告/);
  assert.match(html, /规则报告 · 模型已降级/);
  assert.match(html, /有证据支持<\/dt><dd[^>]*>1<\/dd>/);
  assert.match(html, /待补材料<\/dt><dd[^>]*>2<\/dd>/);
  assert.match(html, /岗位要求<\/dt><dd[^>]*>5<\/dd>/);
  assert.match(html, /部分支持 1 项 · 未覆盖或需复核 1 项/);
  assert.match(html, /<details[^>]*><summary[^>]*>报告时间、材料版本与判断范围<\/summary>/);
  assert.match(html, /报名服务 · 第2版/);
  assert.match(html, /保留的完整判断/);
  assert.equal(JSON.stringify(report), original);
});

const summary = {
  id: "report-a", jobId: "job-a", jobTitle: "后端开发", candidateName: "甲",
  createdAt: "2026-10-22T10:00:00Z", summary: "已保存的规则分析",
};
test("history card displays server-wide history facts and fixed versions only when recorded", () => {
  const html = render(React.createElement(ReportHistoryCard, { report: {
    ...summary, isLatestForJob: false, jobReportCount: 27,
    materials: [
      { kind: "project", id: "version-a111111", title: "同名项目", versionNumber: 1 },
      { kind: "project", id: "version-b222222", title: "同名项目", versionNumber: 2 },
    ],
  }, onSameJob() {} }));
  assert.match(html, /有后续报告/);
  assert.match(html, /同岗位历史（27份）/);
  assert.match(html, /同名项目 · 第1版 · 材料编号 version-/);
  assert.match(html, /同名项目 · 第2版/);
  assert.match(html, /href="\/reports\/report-a"/);
  const unknown = render(React.createElement(ReportHistoryCard, { report: summary }));
  assert.doesNotMatch(unknown, /最新报告|后续报告|固定材料|历史（/);
});
test("comparison is bounded at four, removable and does not mutate the caller's selection", () => {
  const ids = ["a", "b", "c", "d"];
  assert.deepEqual(toggleComparisonCandidate(ids, "e"), ids);
  assert.deepEqual(toggleComparisonCandidate(ids, "b"), ["a", "c", "d"]);
  assert.deepEqual(ids, ["a", "b", "c", "d"]);
  assert.deepEqual(toggleComparisonCandidate(["a"], "b"), ["a", "b"]);
});
test("nearby cell evidence stays in the selected application's frozen requirement and materials", () => {
  const item = {
    requirementId: "r-a", requirementTitle: "容量限制", verdict: "supported",
    explanation: "容量不足时拒绝报名", aiExplanation: null, aiInformationGap: null,
    evidenceList: [{ citationId: "R1-E1", filePath: "version-a/service.py", projectVersionId: "version-a", lineStart: 12, lineEnd: 17, snippet: "raise CapacityError()", contentHash: "hash-a", evidenceType: "project_code" }],
  };
  const application = { id: "application-a", candidateName: "合成甲", report: {
    ...summary, materials: [{ id: "version-a", kind: "project", title: "报名项目", versionNumber: 3 }],
    items: [item, { ...item, requirementId: "r-b", requirementTitle: "不能串入的其他要求", evidenceList: [{...item.evidenceList[0], snippet:"DO_NOT_LEAK"}] }],
  } };
  const html = render(React.createElement(SelectedRequirementEvidence, { application, requirementId: "r-a" }));
  assert.match(html, /合成甲 · 容量限制/);
  assert.match(html, /报名项目/);
  assert.match(html, /第12–17行/);
  assert.match(html, /raise CapacityError/);
  assert.doesNotMatch(html, /DO_NOT_LEAK|不能串入的其他要求/);
  assert.match(html, /href="#selected-application-report"/);
  const missing = render(React.createElement(SelectedRequirementEvidence, { application, requirementId: "other-version-r" }));
  assert.match(missing, /不同报告的要求版本可能不同/);
  assert.doesNotMatch(missing, /raise CapacityError/);
});


test("zero matches retain the selected requirement label and exact filter value", () => {
  const html = render(React.createElement(RequirementFocusSelect, {
    dimensions: [], value: "req-capacity", selectedLabel: "容量不足处理", onChange() {},
  }));
  assert.match(html, /<option value="req-capacity" selected="">容量不足处理<\/option>/);
  assert.doesNotMatch(html, /<option value="" selected=/);
  const other = render(React.createElement(RequirementFocusSelect, {
    dimensions: [{requirementId: "req-other", title: "另一要求", skill: "SQL"}],
    value: "req-capacity", selectedLabel: "容量不足处理", onChange() {},
  }));
  assert.match(other, /value="req-capacity" selected=""/);
  assert.match(other, /value="req-other"/);
  const unknown = render(React.createElement(RequirementFocusSelect, {
    dimensions: [], value: "legacy-requirement", selectedLabel: "", onChange() {},
  }));
  assert.match(unknown, /已选要求（当前结果未包含）/);
  const reset = render(React.createElement(RequirementFocusSelect, {
    dimensions: [], value: "", selectedLabel: "旧标签", onChange() {},
  }));
  assert.match(reset, /<option value="" selected="">全部要求<\/option>/);
  assert.doesNotMatch(reset, /旧标签/);
});


for (const [aiStatus, fallback, accepted] of [
  ["invalid_citations", false, false], ["rejected", false, false],
  ["validated", true, false], ["validated", false, true],
]) {
  test(`nearby evidence uses only accepted AI interpretation (status=${aiStatus}, fallback=${fallback})`, () => {
    const application = { id: "snapshot-application", candidateName: "合成评审甲", report: {
      ...summary, aiFallbackUsed: fallback, materials: [], items: [{
        requirementId: "sql-requirement", requirementTitle: "SQL事务", verdict: "supported",
        explanation: "规则说明：源码包含显式回滚调用", evidenceLevelGap: "规则缺口：未核实实际运行环境",
        aiExplanation: "模型原文：应当仅在有效状态显示", aiInformationGap: "模型缺口：应当仅在有效状态显示",
        aiStatus, evidenceList: [],
      }],
    }};
    const original = JSON.stringify(application);
    const html = render(React.createElement(SelectedRequirementEvidence, { application, requirementId: "sql-requirement" }));
    if (accepted) {
      assert.match(html, /AI解释/);
      assert.match(html, /模型原文：应当仅在有效状态显示/);
      assert.match(html, /模型缺口：应当仅在有效状态显示/);
      assert.doesNotMatch(html, /规则说明：源码包含显式回滚调用/);
    } else {
      assert.match(html, /规则解释/);
      assert.match(html, /规则说明：源码包含显式回滚调用/);
      assert.match(html, /规则缺口：未核实实际运行环境/);
      assert.doesNotMatch(html, /模型原文：应当仅在有效状态显示|模型缺口：应当仅在有效状态显示|AI解释/);
    }
    assert.equal(JSON.stringify(application), original, "rendering must not rewrite the fixed snapshot");
  });
}


for (const [aiStatus, fallback, accepted] of [
  ["invalid_citations", false, false], ["rejected", false, false],
  ["validated", true, false], ["validated", false, true],
]) {
  test(`full saved requirement uses the same interpretation guard (status=${aiStatus}, fallback=${fallback})`, () => {
    const item = {
      requirementId: "fixed-sql", requirementTitle: "持久化事务", skill: "SQL", verdict: "supported", finalScore: 65,
      explanation: "规则依据：SQL事务包含回滚调用", evidenceLevelGap: "规则缺口：实际运行环境待核对",
      aiExplanation: "MODEL_FULL_EXPLANATION", aiInformationGap: "MODEL_FULL_GAP", aiStatus,
      evidenceList: [{ citationId: "R1-E1", filePath: "version-a/storage.py", projectVersionId: "version-a", lineStart: 20, lineEnd: 25, snippet: "connection.rollback()", contentHash: "fixed-hash", evidenceType: "project_code" }],
    };
    const report = { ...summary, aiFallbackUsed: fallback, materials: [], items: [item] };
    const before = JSON.stringify(report);
    const html = render(React.createElement(SavedRequirementDetail, { item, report }));
    if (accepted) {
      assert.match(html, /AI解释/);
      assert.match(html, /MODEL_FULL_EXPLANATION/);
      assert.match(html, /MODEL_FULL_GAP/);
    } else {
      assert.match(html, /规则解释/);
      assert.match(html, /规则依据：SQL事务包含回滚调用/);
      assert.match(html, /规则缺口：实际运行环境待核对/);
      assert.doesNotMatch(html, /MODEL_FULL_EXPLANATION|MODEL_FULL_GAP|AI解释/);
    }
    assert.match(html, /R1-E1/);
    assert.match(html, /第20—25行/);
    assert.match(html, /connection.rollback/);
    assert.match(html, /fixed-hash/);
    assert.equal(JSON.stringify(report), before);
  });
}

const { default: CandidatePairComparison } = await import('../src/components/CandidatePairComparison.tsx');
const { comparableRadarAxes } = await import('../src/lib/application-comparison.ts');
const pairCandidate = (id, secondVerdict='supported') => ({
 id, jobId:'job-a', candidateName:`合成${id}`, reportId:`report-${id}`, comparisonBasis:'same-frozen-basis',fixedRequirementBasisComplete:true,
 dimensions:[{requirementId:'r1',title:'接口实现',skill:'FastAPI',weight:4,verdict:'supported',score:65,formulaVersion:'v3'}, {requirementId:'r2',title:'业务测试',skill:'pytest',weight:3,verdict:secondVerdict,score:secondVerdict==='gap'?0:40,formulaVersion:'v3'}, {requirementId:'r3',title:'SQL持久化',skill:'SQL',weight:2,verdict:'unsupported',score:null,formulaVersion:'v3'}],
 report:{id:`report-${id}`,analysisMode:'rules',aiFallbackUsed:true,materials:[{kind:'project',id:`version-${id}`,title:`项目${id}`,versionNumber:2}],
 items:['r1','r2','r3'].map((r,i)=>({requirementId:r,requirementTitle:r,verdict:i===1?secondVerdict:'supported',finalScore:i===1&&secondVerdict==='gap'?0:40,aiStatus:'validated',aiExplanation:'UNADOPTED_AI',aiInformationGap:'UNADOPTED_GAP',explanation:`${id}-${r}-原判断`,evidenceLevelGap:`${id}-${r}-核对事项`,evidenceList:i===1&&secondVerdict==='gap'?[]:[{citationId:`${id}-${r}-E1`,filePath:`version-${id}/service.py`,projectVersionId:`version-${id}`,lineStart:12,lineEnd:28,snippet:`${id}-${r}-source`,contextComplete:true}]}))}
});
test('two fixed reports use identity colors and linked requirement columns, with missing material not plotted as zero',()=>{
 const candidates=[pairCandidate('A'),pairCandidate('B','gap')];
 const html=render(React.createElement(CandidatePairComparison,{candidates,busy:false,onOpen(){},initialIds:['r2']}));
 assert.match(html,/双人同轴材料支持度雷达/);assert.match(html,/#4f46e5/);assert.match(html,/#c2410c/);assert.doesNotMatch(html,/<polygon/);
 assert.match(html,/A-r2-source/);assert.doesNotMatch(html,/A-r1-source/);assert.match(html,/B-r2-原判断/);assert.match(html,/当前授权报告没有对应引用/);
 assert.match(html,/项目A/);assert.match(html,/第12–28行/);assert.doesNotMatch(html,/UNADOPTED_AI|UNADOPTED_GAP/);
 assert.doesNotMatch(html,/aria-label="合成B · pytest/);assert.match(html,/aria-label="合成A · pytest/);
 assert.equal((html.match(/<details[^>]*\bopen[= >]/g)||[]).length,1);
});
test('mismatching basis or axes never overlay; selection alone never claims a report is opened',()=>{
 const a=pairCandidate('A'),b=pairCandidate('B');
 for(const changed of [{...b,comparisonBasis:'other'}, {...b,dimensions:b.dimensions.map((d,i)=>i===1?{...d,weight:5}:d)}, {...b,dimensions:b.dimensions.map((d,i)=>i===1?{...d,requirementId:'different'}:d)}]){
 assert.equal(comparableRadarAxes(a,changed),false);
 const html=render(React.createElement(CandidatePairComparison,{candidates:[a,changed],busy:false,onOpen(){}}));assert.match(html,/比较依据不同/);assert.doesNotMatch(html,/双人同轴材料支持度雷达/);assert.match(html,/合成A的岗位要求/);assert.match(html,/合成B的岗位要求/);
 }
 const html=render(React.createElement(CandidatePairComparison,{candidates:[a,{...b,report:undefined}],busy:false,onOpen(){}}));assert.match(html,/打开两份授权报告/);assert.doesNotMatch(html,/A-r1-source|双人同轴材料支持度雷达/);
});

test('incomplete historical requirement facts cannot produce a same-axis comparison',()=>{
 const a=pairCandidate('A'),b={...pairCandidate('B'),fixedRequirementBasisComplete:undefined};
 assert.equal(comparableRadarAxes(a,b),false);
 const html=render(React.createElement(CandidatePairComparison,{candidates:[a,b],busy:false,onOpen(){}}));
 assert.match(html,/比较依据不足/);assert.doesNotMatch(html,/双人同轴材料支持度雷达/);assert.match(html,/合成A的岗位要求/);
});

test('equal citation aliases in two fixed reports get candidate-scoped links and preserve full accepted text',()=>{
 const candidates=['A','B'].map(id=>{const c=pairCandidate(id);c.report.aiFallbackUsed=false;c.report.analysisMode='ai_evidence';c.report.items[0]={...c.report.items[0],aiExplanation:'R1-E1 '+('实际材料解释。'.repeat(30))+'原文结尾',aiCitationIds:['R1-E1'],aiInformationGap:'运行待核验',evidenceList:[{...c.report.items[0].evidenceList[0],citationId:'R1-E1'}]};return c;});
 const before=JSON.stringify(candidates);
 const html=render(React.createElement(CandidatePairComparison,{candidates,busy:false,onOpen(){}}));
 for(const id of ['A','B']) {assert.match(html,new RegExp(`href="#pair-${id}-citation-R1-E1"`));assert.match(html,new RegExp(`id="pair-${id}-citation-R1-E1"`));}
 assert.match(html,/原文结尾/);assert.doesNotMatch(html,/href="#citation-R1-E1"/);assert.equal(JSON.stringify(candidates),before);
});
