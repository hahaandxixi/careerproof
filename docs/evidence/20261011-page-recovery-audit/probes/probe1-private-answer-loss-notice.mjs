// 探针1：PrivateAnswerDraft 组装层在"隐藏→恢复可见"序列中，clear() 发布的
// "未保存的修改已丢弃"声明是否对用户可见。
// 复现 PrivateAnswerDraft.tsx visibilitychange 组装：hidden→clear()；visible→activate()+load()。
// 全部为纯函数调用，无浏览器/服务/DB。resolver hooks 与 tests/*.test.mjs 相同（sucrase 转译 TS）。
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(here, "../../../../jianli/src");
const require = createRequire(import.meta.url);
const { transform } = require(path.resolve(here, "../../../../jianli/node_modules/sucrase/dist/index.js"));

registerHooks({
  resolve(specifier, context, nextResolve) {
    if ((specifier.startsWith("./") || specifier.startsWith("../")) && !path.extname(specifier)) {
      for (const suffix of ["", ".ts", ".tsx", "/index.ts", "/index.tsx"]) {
        try { return nextResolve(new URL(specifier + suffix, context.parentURL).href, context); } catch {}
      }
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

const { createPrivateAnswerSession, initialPrivateAnswerState } = await import(
  pathToFileURL(path.join(SRC, "lib/private-answer-workflow.ts")).href
);

let getDraftCalls = 0;
let failNext = false;
const settle = () => new Promise(resolve => setTimeout(resolve, 0));
let current = initialPrivateAnswerState;
const session = createPrivateAnswerSession({
  getDraft: async () => {
    getDraftCalls++;
    if (failNext) throw new TypeError("Failed to fetch");
    return { text: "服务器版本", revision: 1, updatedAt: "2026-10-11T00:00:00Z", references: [] };
  },
  saveDraft: async () => { throw new Error("unused"); },
  listReferences: async () => [],
  errorMessage: () => "读取失败",
}, state => { current = state; });

// 初始加载（组件挂载；PrivateAnswerDraft.tsx:47-49 activate 后立即 load）
session.activate();
void session.load("task-1", { crossJob: false, hasTargetReport: false });
await settle();
assert.equal(current.text, "服务器版本");

// 用户开始编辑（未保存）
session.setText("用户未保存的重要编辑");
assert.equal(current.text, "用户未保存的重要编辑");

// visibilitychange → hidden：组件调用 session.clear()
session.clear();
assert.match(current.notice, /未保存的修改已丢弃/, "workflow 层确实发布了丢弃声明");

// visibilitychange → visible：组件立即 activate()+load()（PrivateAnswerDraft.tsx:55-57）
session.activate();
const loadPromise = session.load("task-1", { crossJob: false, hasTargetReport: false });
// load() 的第一个 set({reading:true, notice:""}) 是同步执行的：
assert.equal(current.notice, "", "恢复可见的同一事件循环内，丢弃声明已被 load 清空——用户从未看到它");
assert.equal(current.reading, true, "此时进入读取态");
await loadPromise;
assert.equal(getDraftCalls, 2);
assert.equal(current.text, "服务器版本", "读取回执以服务器版本覆盖本地编辑（未保存编辑丢失）");
assert.ok(!/丢弃/.test(current.notice), "load 完成后 notice 是读取提示，丢弃声明不可恢复");
assert.ok(!/丢弃/.test(current.error + current.notice), "成功路径的最终可见文本中不含丢弃声明");

// 第二序列：clear → load 失败（网络中断）。用户看到的只有 error，仍无丢弃声明。
session.setText("再次未保存的编辑");
session.clear();
assert.match(current.notice, /未保存的修改已丢弃/);
session.activate();
failNext = true;
const failing = session.load("task-1", { crossJob: false, hasTargetReport: false });
assert.equal(current.notice, "", "失败路径同样在 load 首段同步清掉丢弃声明");
assert.equal(current.text, "", "文本框已回空（initial 文本）");
await failing;
console.log("序列2结束 notice=%j error=%j text=%j", current.notice, current.error, current.text);
assert.ok(!/丢弃/.test(current.notice + current.error), "网络中断恢复失败时用户也看不到丢弃声明");

console.log("PROBE1 PASS：丢弃声明在两种恢复路径下都对用户不可见；未保存编辑静默丢失。");
