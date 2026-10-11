// 探针3：补证任务"目标岗位选择器"分页在 jobTotal 过期偏大时允许发起越界页请求，
// 服务端 /jobs 无页码裁剪（对比 notifications 有），前端回执后也不自纠页码，
// 结果是停留在一个空页码上（可手动"上一页"恢复，无自动恢复）。
// 纯函数探针，无网络。
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../../..");
const require = createRequire(import.meta.url);
const { transform } = require(path.join(ROOT, "jianli/node_modules/sucrase/dist/index.js"));

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

const { growthJobPageBounds, growthJobListQuery } = await import(
  pathToFileURL(path.join(ROOT, "jianli/src/lib/growth-workflow.ts")).href
);

// 常规序：total=25（3页），页1 hasNext 允许翻到页2。
const page1 = growthJobPageBounds(25, 1, 10);
assert.equal(page1.hasNext, true, "total=25 时页1允许翻页2");

// 竞态：用户翻到页2后，服务端 total 缩为 12（13 个岗位被下架）。
// GrowthWorkspace 的 jobTotal 仍持有旧值 25；用户点"下一页"时
// growthJobPageBounds(25, 2, 10) 判 hasNext=20<25=true，放行页3请求。
// 页3 offset=20 已越出服务端实际 12 条 —— 后端 jobs.py:102-115 无 page=min() 裁剪，
// 返回空 items 且 page 原样回显，前端 setJobPage(3) 停在空页。
const stalePage2 = growthJobPageBounds(25, 2, 10);
assert.equal(stalePage2.hasNext, true, "过期 total=25 下页2的 hasNext 仍为 true：以过期 total 判界放行越界的页3请求");
// 页3回执后 jobTotal 更新为 12：
const afterReceipt = growthJobPageBounds(12, 3, 10);
assert.equal(afterReceipt.hasNext, false, "回执后下一页被禁用（自动恢复不存在）");
assert.equal(afterReceipt.hasPrevious, true, "上一页可用，构成唯一恢复路径");

// 请求参数合法性对照：翻页请求确实是 page=3（offset=20 越出服务端实际总量）。
assert.deepEqual(growthJobListQuery("", 3), { page: 3, pageSize: 10 });

console.log("PROBE3 PASS：jobTotal 过期偏大时 hasNext 放行越界页请求；后端无裁剪、前端不自纠，停留在空页码（手动上一页可恢复）。");
