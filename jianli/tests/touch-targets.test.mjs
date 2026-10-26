// 触控目标：项目标准是 44px（min-h-11）。首页 CTA、候选人选择器、选择开关、账户菜单都已显式声明，
// 但 .btn / .btn-secondary 原先只靠 py-2.5 + text-sm（约 40px），低于项目自身标准。
// 这两条契约测试防止将来改样式时又退回 40px。纯静态读取 globals.css，不启动浏览器。
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(fileURLToPath(new URL("../src/app/globals.css", import.meta.url)), "utf8");

function ruleBody(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`(?:^|\\n)\\s*${escaped}\\s*\\{([^}]*)\\}`).exec(css);
  assert.ok(match, `未找到样式规则 ${selector}`);
  return match[1];
}

test("主按钮与次级按钮满足 44px 触控高度（min-h-11）", () => {
  for (const selector of [".btn", ".btn-secondary"]) {
    const body = ruleBody(selector);
    assert.ok(/\bmin-h-11\b/.test(body), `${selector} 必须声明 min-h-11（44px），当前：${body.trim()}`);
  }
});

test("候选人选择与选择开关保持 44px，避免回退", () => {
  const body = ruleBody(".candidate-select, .selection-toggle");
  assert.ok(/\bmin-h-11\b/.test(body), `选择器必须保持 min-h-11，当前：${body.trim()}`);
});
