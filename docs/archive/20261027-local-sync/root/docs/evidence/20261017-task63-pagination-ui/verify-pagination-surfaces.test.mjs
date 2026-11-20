// task63 static verification: the five paginated lists must render a pagination control
// and state their current-page filter scope. This is NOT a browser acceptance — it only
// proves the control and the scope copy exist in source, which is what can be decided
// offline. Real 390px rendering is reported as blocked in review.md.

import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
function findFrontend(start) {
  let cursor = start;
  for (let depth = 0; depth < 8; depth += 1) {
    if (fs.existsSync(path.join(cursor, "jianli", "package.json"))) return path.join(cursor, "jianli");
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }
  throw new Error(`cannot locate jianli frontend above ${start}`);
}
const SRC = path.join(findFrontend(here), "src", "components");
const read = name => fs.readFileSync(path.join(SRC, name), "utf8");

const LISTS = [
  { file: "ApplicationList.tsx", label: "投递分页" },
  { file: "ApplicationBoard.tsx", label: "候选人分页" },
  { file: "ReportList.tsx", label: "报告分页" },
  { file: "GrowthWorkspace.tsx", label: "补证任务分页" },
];

test("each student/enterprise list renders ListPagination with its own label", () => {
  for (const { file, label } of LISTS) {
    const source = read(file);
    assert.ok(source.includes("ListPagination"), `${file} must render ListPagination`);
    assert.ok(source.includes(`label="${label}"`), `${file} must label its control as ${label}`);
  }
});

test("the enterprise candidate board states its filter only covers the current page", () => {
  const source = read("ApplicationBoard.tsx");
  assert.match(source, /筛选仅作用于当前页/, "current-page filter scope must be stated");
  assert.match(source, /每页20份/, "page size must be stated");
  // The notification-injected candidate must not inflate page membership.
  assert.match(source, /pageItemCount/, "extra notification targets must be excluded from page count");
  assert.match(source, /不计入本页记录数/, "the extra-row rule must be visible to the reader");
});

test("notification centre paginates and labels its empty states", () => {
  const source = read("NotificationCenter.tsx");
  assert.match(source, /第 \{page\} 页/, "notification centre must show the page number");
  assert.match(source, /暂无未读通知。/, "unread empty state must be explicit");
  assert.match(source, /暂无通知，新的投递事件会显示在这里。/, "all-seen empty state must be explicit");
  // Next-page guard derives from server paging, not from local array length.
  assert.match(source, /page \* data\.pageSize >= data\.total/, "next must be bounded by server total");
});

test("pagination helper disables next on an exact final page and reports 0 records when empty", async () => {
  const { pageBounds } = await import(
    pathToFileURL(path.join(findFrontend(here), "src", "lib", "list-pagination.js")).href
  );
  assert.deepEqual(pageBounds({ total: 40, page: 2, pageSize: 20 }), {
    pages: 2, previous: true, next: false, start: 21, end: 40,
  });
  assert.deepEqual(pageBounds({ total: 0, page: 1, pageSize: 20 }), {
    pages: 1, previous: false, next: false, start: 0, end: 0,
  });
});
