// 键盘可达性的两个单点：
// 1) 全局 :focus-visible 是唯一焦点提示来源；删掉它，全站键盘用户就看不见焦点在哪。
// 2) outline-none 必须同行配回 focus:ring 或 focus-visible:outline，否则该元素焦点不可见。
// 纯静态读取源码，不启动浏览器；变异验证见交付说明（删掉全局规则时该测试会红）。
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const srcRoot = fileURLToPath(new URL("../src", import.meta.url));
const globals = readFileSync(join(srcRoot, "app/globals.css"), "utf8");

test("全局 :focus-visible 必须给出可见描边与偏移", () => {
  // 只认行首的全局选择器：`.site-brand:focus-visible` 这类限定规则不能替代全局兜底。
  const match = /(?:^|\n)[ \t]*:focus-visible\s*\{([^}]*)\}/.exec(globals);
  assert.ok(match, "globals.css 必须定义**全局** :focus-visible 规则（行首选择器），否则未单独声明焦点的元素不可见");
  assert.ok(/outline:\s*[2-9]px\s+solid/.test(match[1]), `焦点描边至少 2px 实线：${match[1].trim()}`);
  assert.ok(/outline-offset:\s*[1-9]/.test(match[1]), `焦点描边必须留出偏移，避免贴边不可见：${match[1].trim()}`);
});

test("每处 outline-none 都必须同行配回焦点样式", () => {
  const offenders = [];
  const walk = dir => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) { walk(path); continue; }
      if (!/\.(tsx|ts|css)$/.test(name)) continue;
      const lines = readFileSync(path, "utf8").split("\n");
      lines.forEach((line, index) => {
        if (!line.includes("outline-none")) return;
        if (/focus:ring|focus-visible:outline/.test(line)) return;
        offenders.push(`${relative(srcRoot, path)}:${index + 1}`);
      });
    }
  };
  walk(srcRoot);
  assert.deepEqual(offenders, [], `这些位置用 outline-none 去掉了焦点描边却没有替代样式：${offenders.join(", ")}`);
});
