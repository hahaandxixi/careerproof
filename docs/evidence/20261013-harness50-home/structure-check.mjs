// 首页 JSX 结构性自检（只读 page.tsx，不修改任何源码）
// 用途：在未运行 typecheck/build 的前提下，静态核对标签配对、链接目标与 44px 触控类。
import { readFileSync } from "node:fs";

const target = process.argv[2];
const source = readFileSync(target, "utf8");

// 1) 标签配对检查
const tagPattern = /<\/?([A-Za-z][A-Za-z0-9]*)\b[^>]*?(\/?)>/g;
const stack = [];
const errors = [];
let match;
while ((match = tagPattern.exec(source)) !== null) {
  const raw = match[0];
  const name = match[1];
  const selfClosing = match[2] === "/" || raw.endsWith("/>");
  const isClose = raw.startsWith("</");
  if (isClose) {
    const top = stack.pop();
    if (top !== name) errors.push(`闭合不匹配: </${name}> 对应 <${top ?? "无"}> (offset ${match.index})`);
  } else if (!selfClosing) {
    stack.push(name);
  }
}
if (stack.length) errors.push(`未闭合标签: ${stack.join(", ")}`);

// 2) 花括号 / 圆括号 / 方括号平衡
for (const [open, close, label] of [["{", "}", "花括号"], ["(", ")", "圆括号"], ["[", "]", "方括号"]]) {
  const o = [...source].filter((c) => c === open).length;
  const c = [...source].filter((ch) => ch === close).length;
  if (o !== c) errors.push(`${label}不平衡: ${open}=${o} ${close}=${c}`);
}

// 3) 链接与触控目标清单
const links = [...source.matchAll(/<Link\s+href="([^"]+)"/g)].map((m) => m[1]);
const hrefs = [...source.matchAll(/href="(\/[^"]*)"/g)].map((m) => m[1]);
const minH = (source.match(/min-h-\[44px\]/g) || []).length;
const useClient = /"use client"/.test(source);
const img = /<img|next\/image/.test(source);

console.log(`目标文件: ${target}`);
console.log(`<Link> 数量: ${links.length}`);
console.log(`Link 目标: ${[...new Set(links)].sort().join(" ")}`);
console.log(`全部站内 href: ${[...new Set(hrefs)].sort().join(" ")}`);
console.log(`min-h-[44px] 出现次数: ${minH}`);
console.log(`含 use client: ${useClient}（预期 false，首页应为服务端组件）`);
console.log(`使用图片: ${img}（预期 false）`);
console.log(errors.length ? `结构问题:\n- ${errors.join("\n- ")}` : "结构检查: 标签配对与括号平衡通过");
process.exitCode = errors.length ? 1 : 0;
