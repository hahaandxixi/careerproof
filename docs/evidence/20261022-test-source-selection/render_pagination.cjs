// Render the accepted real component, rather than checking source-code strings.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { createRequire } = require("node:module");
const localRequire = createRequire(path.resolve("package.json"));
const React = localRequire("react");
const { renderToStaticMarkup } = localRequire("react-dom/server");
const { transform } = localRequire("sucrase");
const source = path.resolve("src/components/ListPagination.tsx");
const code = transform(fs.readFileSync(source, "utf8"), {
  transforms: ["typescript", "jsx", "imports"], jsxRuntime: "classic", filePath: source,
}).code;
const componentModule = { exports: {} };
const componentRequire = id => localRequire(id.startsWith("@/") ? `./src/${id.slice(2)}` : id);
new Function("require", "module", "exports", "React", code)(
  componentRequire, componentModule, componentModule.exports, React,
);
const Component = componentModule.exports.default;
const render = (value, busy = false) => renderToStaticMarkup(React.createElement(Component, {
  value, busy, label: "投递分页", onPage: () => {},
}));
const beyond = render({ total: 5, page: 2, pageSize: 20 });
assert.ok(beyond.includes("本页记录 0–0"));
assert.ok(beyond.includes("当前页已超出范围，请返回上一页"));
assert.ok(!beyond.includes("21–5"));
const buttons = [...beyond.matchAll(/<button([^>]*)>([^<]+)<\/button>/g)];
assert.equal(buttons.length, 2);
assert.ok(!buttons[0][1].includes("disabled"));
assert.ok(buttons[1][1].includes("disabled"));
const normal = render({ total: 101, page: 6, pageSize: 20 });
assert.ok(normal.includes("本页记录 101–101"));
assert.ok(!normal.includes("超出范围"));
fs.writeFileSync(path.join(__dirname, "pagination-rendered.html"), beyond + "\n" + normal + "\n");
console.log("Real ListPagination render: out-of-range readout, previous/next, normal final page PASS");
