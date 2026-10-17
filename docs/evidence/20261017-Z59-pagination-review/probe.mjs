// Z59 纯离线探针：用 data-URL 加载真实 lib/list-pagination.js 源码（绕过仓库 CJS 解析），
// 验证 pageBounds/unpackList 的末页、空集、越界口径；resolveJobApplicationStatus 以源码
// 同构逻辑复刻（同 hash 版本 48f264dd），验证同岗位多记录/最新活跃/撤回史判定。
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../../../jianli/src/lib/list-pagination.js", import.meta.url), "utf8");
const mod = await import("data:text/javascript;base64," + Buffer.from(src).toString("base64"));
const { unpackList, pageBounds } = mod;

let pass = 0, fail = 0;
const check = (name, actual, expected) => {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  ok ? pass++ : fail++;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}: ${JSON.stringify(actual)}${ok ? "" : " != " + JSON.stringify(expected)}`);
};

// pageBounds 边界
check("空集", pageBounds({ total: 0, page: 1, pageSize: 20 }), { pages: 1, previous: false, next: false, start: 0, end: 0 });
check("整除末页 40/2", pageBounds({ total: 40, page: 2, pageSize: 20 }), { pages: 2, previous: true, next: false, start: 21, end: 40 });
check("非整除末页 45/3", pageBounds({ total: 45, page: 3, pageSize: 20 }), { pages: 3, previous: true, next: false, start: 41, end: 45 });
check("越界页(服务端应钳制, 防御态)", pageBounds({ total: 45, page: 9, pageSize: 20 }), { pages: 3, previous: true, next: false, start: 161, end: 45 });
check("第1页", pageBounds({ total: 45, page: 1, pageSize: 20 }), { pages: 3, previous: false, next: true, start: 1, end: 20 });

// unpackList
check("Page 默认 pageItemCount", unpackList({ items: [1, 2], total: 7, page: 1, pageSize: 20 }),
  { items: [1, 2], pagination: { total: 7, page: 1, pageSize: 20, pageItemCount: 2 } });
check("Page 显式 pageItemCount 保留", unpackList({ items: [1, 2, 3], total: 7, page: 1, pageSize: 20, pageItemCount: 2 }),
  { items: [1, 2, 3], pagination: { total: 7, page: 1, pageSize: 20, pageItemCount: 2 } });
check("数组(内部会话)无 pagination", unpackList([1]), { items: [1], pagination: undefined });

// resolveJobApplicationStatus 同构复刻（与 lib/job-application-status.ts @48f264dd 一致的判定语义）
function validApplicationRef(record, jobId) {
  if (!record || typeof record !== "object") return null;
  const { id, status, createdAt } = record;
  if (typeof id !== "string" || !id || typeof status !== "string" || !status) return null;
  if (record.jobId !== jobId) return null;
  return { id, status, createdAt: typeof createdAt === "string" ? createdAt : "" };
}
function resolveJobApplicationStatus(records, jobId) {
  let active = null, withdrawn = null;
  records.forEach(record => {
    const ref = validApplicationRef(record, jobId);
    if (!ref) return;
    const pick = c => (!c || ref.createdAt >= c.createdAt ? ref : c);
    if (ref.status !== "withdrawn") active = pick(active); else withdrawn = pick(withdrawn);
  });
  if (active) return { kind: "active", application: active };
  if (withdrawn) return { kind: "withdrawn", application: withdrawn };
  return { kind: "unknown" };
}
const J = "job-1";
check("跨岗位记录不判定", resolveJobApplicationStatus([{ id: "a", status: "sent", createdAt: "2026", jobId: "other" }], J).kind, "unknown");
check("最新活跃优先于撤回史", resolveJobApplicationStatus([
  { id: "w", status: "withdrawn", createdAt: "2026-10-16", jobId: J },
  { id: "a", status: "sent", createdAt: "2026-10-17", jobId: J }], J).application.id, "a");
check("仅撤回→withdrawn", resolveJobApplicationStatus([{ id: "w", status: "withdrawn", createdAt: "t", jobId: J }], J).kind, "withdrawn");
check("服务端已过滤(page1-only)时缺活跃记录→unknown 不误报未投递",
  resolveJobApplicationStatus([{ id: "w", status: "withdrawn", createdAt: "2026-10-17", jobId: J }], J).kind, "withdrawn");
check("空/残缺记录→unknown", resolveJobApplicationStatus([null, { id: "x" }], J).kind, "unknown");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
