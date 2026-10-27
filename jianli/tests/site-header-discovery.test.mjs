// Render the actual header with controlled identities; no network, effects or browser claims.
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { transform } = require("sucrase");
const source = readFileSync(new URL("../src/components/SiteHeader.tsx", import.meta.url), "utf8");

function render(role, status = role ? "authenticated" : "anonymous") {
  const Link = ({ children, ...props }) => React.createElement("a", props, children);
  const modules = {
    react: React,
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: Link },
    "next/navigation": { usePathname: () => "/jobs", useRouter: () => ({}) },
    "./AuthProvider": { useAuth: () => ({ user: role ? { role, displayName: "合成身份" } : null, status, logout() {}, reload() {} }) },
    "./NotificationLink": { __esModule: true, default: ({ render }) => render(2) },
    "./StudentAccountMenu": { __esModule: true, default: () => React.createElement("span", null, "学生账户") },
    "./AccountMenu": { __esModule: true, default: () => React.createElement("span", null, "企业账户") },
    "./LoginLink": { __esModule: true, default: ({ register, children, ...props }) => React.createElement("a", { ...props, href: register ? "/register" : "/login" }, children) },
    "@/lib/api/client": { errorMessage: String },
  };
  const mod = { exports: {} };
  new Function("require", "module", "exports", transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code)(id => {
    assert.ok(id in modules, id); return modules[id];
  }, mod, mod.exports);
  return renderToStaticMarkup(React.createElement(mod.exports.default));
}

test("public header has one discovery entry while students retain exactly four primary routes", () => {
  const anonymous = render(null);
  assert.ok(anonymous.includes('href="/login"') && anonymous.includes('href="/register"'));
  assert.ok(!anonymous.includes("交互示例") && !anonymous.includes('href="/growth"'));
  const primary = render("student").match(/<nav aria-label="主导航"[\s\S]*?<\/nav>/)[0];
  assert.deepEqual([...primary.matchAll(/href="([^"]+)"/g)].map(match => match[1]), ["/portfolio", "/jobs", "/reports", "/applications"]);
  assert.ok(primary.includes('aria-current="page"'));
});

test("enterprise and admin retain their original routes and authentication failures offer recovery", () => {
  for (const role of ["enterprise", "admin"]) {
    const html = render(role);
    for (const href of ["/jobs", "/jobs/mine", "/jobs/new"]) assert.ok(html.includes(`href="${href}"`));
    assert.ok(!html.includes('href="/portfolio"'));
    assert.equal(html.includes('href="/reports"'), role === "admin");
  }
  assert.ok(render(null, "error").includes("连接异常 · 重试"));
});
