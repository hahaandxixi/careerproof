// 企业端报告区的可见信息必须可核对：本次使用了哪几份材料、证据的材料身份、
// 以及已发送回复的类型与定位条数。缺信息时如实写未记录，不猜测归属。
// 测试环境没有浏览器 DOM 且禁止安装依赖：用 sucrase 同步转译后渲染真实组件，不匹配源码字符串。
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
const board = await import(pathToFileURL(path.join(SRC, "components/ApplicationBoard.tsx")).href);

const resume = { kind: "resume", id: "3f9c1a2bffffffff", title: "张小满的简历", versionNumber: 2 };
const project = { kind: "project", id: "7e10c4d8eeeeeeee", title: "校园活动报名服务", versionNumber: 2, materialRole: "portfolio" };

test("企业端能看出本次投递固定了哪几份材料：类别、标题、版本与材料编号", () => {
  const html = renderToStaticMarkup(React.createElement(board.MaterialVersionSummary, { materials: [resume, project] }));
  assert.ok(html.includes("本次使用的材料版本（2份）"), html);
  assert.ok(html.includes("简历 · 张小满的简历 · 第 2 版 · 材料编号 3f9c1a2b"), html);
  assert.ok(html.includes("个人项目 / 作品 · 校园活动报名服务 · 第 2 版 · 材料编号 7e10c4d8"), html);
  assert.ok(html.includes("补证或上传新版不会改写本报告"), "必须说明新版不改写本报告");
});

test("企业端不得提供材料原文预览入口（企业无材料库访问权）", () => {
  const html = renderToStaticMarkup(React.createElement(board.MaterialVersionSummary, { materials: [resume] }));
  assert.ok(html.includes("企业不能预览材料原文"), "必须写明权限边界");
  assert.ok(!html.includes("/materials/"), `不得出现材料预览链接：${html}`);
  assert.ok(!html.includes("<a "), `材料汇总区不应有链接：${html}`);
});

test("同名同版本的两份材料仍可区分（靠材料编号，不靠 UUID 全串）", () => {
  const twinA = { kind: "project", id: "aaaaaaaa1111", title: "同名项目", versionNumber: 1 };
  const twinB = { kind: "project", id: "bbbbbbbb2222", title: "同名项目", versionNumber: 1 };
  const html = renderToStaticMarkup(React.createElement(board.MaterialVersionSummary, { materials: [twinA, twinB] }));
  assert.ok(html.includes("材料编号 aaaaaaaa"), html);
  assert.ok(html.includes("材料编号 bbbbbbbb"), html);
  assert.ok(!html.includes("aaaaaaaa1111"), "只显示前8位，不显示整串编号");
});

test("没有材料时不留空折叠块", () => {
  assert.equal(renderToStaticMarkup(React.createElement(board.MaterialVersionSummary, { materials: [] })), "");
  assert.equal(renderToStaticMarkup(React.createElement(board.MaterialVersionSummary, null)), "");
});

test("材料类别措辞与学生报告页一致", () => {
  assert.equal(board.materialKindLabel({ kind: "resume" }), "简历");
  assert.equal(board.materialKindLabel({ kind: "project", materialRole: "reference" }), "第三方参考");
  assert.equal(board.materialKindLabel({ kind: "project", materialRole: "portfolio" }), "个人项目 / 作品");
  assert.equal(board.materialKindLabel({ kind: "project" }), "个人项目 / 作品");
});

test("证据行带材料身份：固定版本与历史版本必须分开表述", () => {
  const fixed = renderToStaticMarkup(React.createElement(board.EvidenceMaterialIdentity, {
    evidence: { evidenceType: "静态代码", projectVersionId: "v-2", contentHash: "a1b2c3d4e5f60718" },
  }));
  assert.ok(fixed.includes("证据类型：静态代码"), fixed);
  assert.ok(fixed.includes("材料版本：本报告固定版本"), fixed);
  assert.ok(fixed.includes("内容摘要：a1b2c3d4e5f6"), fixed);
  assert.ok(!fixed.includes("a1b2c3d4e5f60718"), "只显示摘要前12位，不显示整串哈希");

  const historical = renderToStaticMarkup(React.createElement(board.EvidenceMaterialIdentity, {
    evidence: { evidenceType: "静态代码", projectVersionId: null, contentHash: "ffff00001111222" },
  }));
  assert.ok(historical.includes("材料版本：历史版本未记录"), "缺版本时必须如实写未记录，不得写成固定版本");
  assert.ok(!historical.includes("本报告固定版本"), historical);
});

test("内容摘要缺失时不留空标签", () => {
  const html = renderToStaticMarkup(React.createElement(board.EvidenceMaterialIdentity, {
    evidence: { evidenceType: "静态代码", projectVersionId: "v-2", contentHash: "" },
  }));
  assert.ok(html.includes("材料版本：本报告固定版本"), html);
  assert.ok(!html.includes("内容摘要"), `无摘要时不应出现该标签：${html}`);
});

// 企业发送回复后若只显示正文，就无法核对自己发的是"面试邀请"还是"继续沟通"——学生端却能看见类型。
test("已发送回复必须同时显示回应类型，与学生在个人投递里看到的一致", () => {
  for (const [kind, label] of [["continue", "继续沟通"], ["interview", "面试邀请"], ["declined", "暂不推进"]]) {
    const html = renderToStaticMarkup(React.createElement(board.SentReplySummary, {
      replyText: "请补充报名接口的并发测试说明。", replyKind: kind, referenceCount: 0,
    }));
    assert.ok(html.includes("已发送回复"), html);
    assert.ok(html.includes(label), `缺少回应类型「${label}」：${html}`);
    assert.ok(html.includes("请补充报名接口的并发测试说明。"), "必须保留回复正文");
  }
});

test("已发送回复带定位条数，便于核对自己发出去的内容", () => {
  const two = renderToStaticMarkup(React.createElement(board.SentReplySummary, {
    replyText: "见第2项与第3项。", replyKind: "continue", referenceCount: 2,
  }));
  assert.ok(two.includes("含 2 处原报告定位"), two);
  const none = renderToStaticMarkup(React.createElement(board.SentReplySummary, {
    replyText: "整体说明。", replyKind: "continue", referenceCount: 0,
  }));
  assert.ok(!none.includes("原报告定位"), `无定位时不应出现该说明：${none}`);
});

test("没有回复正文时整块不渲染，历史或异常数据不得渲染空引用块", () => {
  assert.equal(renderToStaticMarkup(React.createElement(board.SentReplySummary, { replyText: "", replyKind: "interview", referenceCount: 1 })), "");
});

test("未知回应类型原样显示，不猜测成某个已知类型", () => {
  const html = renderToStaticMarkup(React.createElement(board.SentReplySummary, {
    replyText: "正文", replyKind: "legacy_kind", referenceCount: 0,
  }));
  assert.ok(html.includes("已发送回复 · legacy_kind"), html);
});

// whitespace-pre-wrap 只在空白处换行，长链接或长英文串不会在词内断开，会撑破 390px 容器。
test("长回复必须能在词内换行，不得撑破窄屏容器", () => {
  const longUrl = "https://example.com/" + "a".repeat(120);
  const html = renderToStaticMarkup(React.createElement(board.SentReplySummary, {
    replyText: longUrl, replyKind: "continue", referenceCount: 0,
  }));
  const openTag = /<blockquote[^>]*>/.exec(html)?.[0] ?? "";
  assert.ok(openTag.includes("whitespace-pre-wrap"), `须保留原有换行语义：${openTag}`);
  assert.ok(openTag.includes("break-words"), `pre-wrap 必须配 break-words，否则长链接横向溢出：${openTag}`);
  assert.ok(!/\bwhitespace-nowrap\b/.test(openTag), `不得禁止换行：${openTag}`);
});

// 窄屏下要求×候选人矩阵会横向溢出，没有提示用户会以为只显示了一列。
test("矩阵在窄屏给出横向滑动提示，并说明共有几位候选人", () => {
  const html = renderToStaticMarkup(React.createElement(board.MatrixScrollHint, { count: 3 }));
  assert.ok(html.includes("表格可左右滑动"), html);
  assert.ok(html.includes("全部 3 位候选人"), html);
  assert.ok(/class="[^"]*\bsm:hidden\b/.test(html), `提示只能在小屏显示，桌面端不得占位：${html}`);
});

test("只有一位或没有候选人时不给滑动提示", () => {
  assert.equal(renderToStaticMarkup(React.createElement(board.MatrixScrollHint, { count: 1 })), "");
  assert.equal(renderToStaticMarkup(React.createElement(board.MatrixScrollHint, { count: 0 })), "");
});
