import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { transform } = require("sucrase");
let user = null;
let count = 1200;
const modules = {
  react: React,
  "react/jsx-runtime": require("react/jsx-runtime"),
  "next/link": { __esModule: true, default: props => React.createElement("a", props) },
  "next/navigation": { usePathname: () => "/jobs/mine", useRouter: () => ({}) },
  "./AuthProvider": { useAuth: () => ({ user, status: "authenticated", logout() {}, reload() {} }) },
  "./NotificationLink": { __esModule: true, default: ({ render }) => user && ["student", "enterprise"].includes(user.role) ? render(count) : null },
  "./LoginLink": { __esModule: true, default: ({ register, children, ...props }) => React.createElement("a", { ...props, href: register ? "/register" : "/login" }, children) },
  "@/lib/api/client": { errorMessage: String },
};
function load(name) {
  const source = readFileSync(new URL(`../src/components/${name}.tsx`, import.meta.url), "utf8");
  const code = transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(id => {
    assert.ok(id in modules, `unexpected dependency: ${id}`); return modules[id];
  }, mod, mod.exports);
  modules[`./${name}`] = mod.exports;
  return mod.exports.default;
}
const Menu = load("AccountMenu");
load("StudentAccountMenu");
const Header = load("SiteHeader");
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));

test("enterprise menu preserves exact unread count and identity without student-only routes", () => {
  const name = "很长的合成企业名称".repeat(10);
  const html = render(Menu, { role: "enterprise", name, unreadCount: 1200, busy: true, onLogout() {} });
  assert.match(html, /1200 条未读通知/);
  assert.match(html, /99\+/);
  assert.match(html, /通知（1200 未读）/);
  assert.ok(html.includes(name));
  assert.match(html, /disabled=""/);
  assert.match(html, /退出中…/);
  assert.match(html, /href="\/notifications"/);
  assert.doesNotMatch(html, /工作台|\/portfolio|\/growth|\/reports/);
});

test("unknown and zero unread counts do not fabricate a badge", () => {
  for (const unreadCount of [null, 0]) {
    const html = render(Menu, { role: "enterprise", name: "企业", unreadCount, busy: false, onLogout() {} });
    assert.doesNotMatch(html, /条未读通知|99\+/);
    assert.equal(html.includes("通知（0 未读）"), unreadCount === 0);
    assert.match(html, /退出登录/);
  }
});

test("header keeps each role's original navigation, including admin logout without notification support", () => {
  for (const role of ["student", "enterprise", "admin", null]) {
    user = role ? { id: role, role, displayName: `${role}-identity` } : null;
    count = 7;
    const html = render(Header);
    if (role === "enterprise") {
      assert.match(html, /企业账户/); assert.match(html, /通知（7 未读）/);
      assert.match(html, /aria-current="page"[^>]*>岗位管理/);
      assert.doesNotMatch(html, /我的材料|我的报告|工作台/);
    } else if (role === "student") {
      assert.match(html, /学生账户/); assert.match(html, /我的材料|工作台/);
      assert.doesNotMatch(html, /岗位管理|发布岗位/);
    } else if (role === "admin") {
      assert.match(html, /admin-identity/); assert.match(html, />退出<\/button>/);
      assert.match(html, /岗位管理|匹配报告/);
    } else {
      assert.match(html, /href="\/login"/); assert.match(html, /href="\/register"/);
      assert.doesNotMatch(html, /退出|我的材料|岗位管理/);
    }
  }
});
