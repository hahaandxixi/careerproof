import { test } from "node:test";
import assert from "node:assert/strict";
import { createGrowthRequestGuard, growthTargetJobState, growthJobListQuery, growthJobPageBounds, growthSaveMaterialsPayload, GROWTH_CHANGES } from "../src/lib/growth-workflow.ts";
import { api } from "../src/lib/api/client.ts";

const ORIGINAL = "11111111-1111-1111-1111-111111111111";
const NEW_JOB = "22222222-2222-2222-2222-222222222222";
const OTHER_JOB = "33333333-3333-3333-3333-333333333333";

function baseTask(overrides = {}) {
  return {
    id: "task-1", baseReportId: "report-1", jobId: ORIGINAL, jobTitle: "E2E 岗位A（合成）",
    requirementId: "req-1", requirementTitle: "岗位A要求：能够使用 Python 编写数据处理脚本",
    gap: "缺实现", originalAction: "补充实现", plan: { deliverable: "d", steps: ["s"], acceptanceChecks: ["c"] },
    baseMaterials: [], materials: [], status: "planned",
    analysisTaskId: null, analysisStatus: null, analysisError: null,
    targetReportId: null, comparison: null, createdAt: "2026-10-05T00:00:00Z", boundary: "b",
    ...overrides,
  };
}

test("旧任务（后端未下发目标字段）的有效目标就是原岗位，不显示跨岗位", () => {
  const state = growthTargetJobState(baseTask(), "");
  assert.equal(state.savedTargetJobId, ORIGINAL);
  assert.equal(state.savedTargetJobTitle, "E2E 岗位A（合成）");
  assert.equal(state.crossJob, false);
  assert.equal(state.selectionChanged, false);
  assert.equal(state.locked, false);
});

test("未改后端时同岗位回填 targetJobId 仍视为原岗位", () => {
  const state = growthTargetJobState(baseTask({ targetJobId: ORIGINAL, targetJobTitle: "E2E 岗位A（合成）" }), "");
  assert.equal(state.crossJob, false);
  assert.equal(state.selectionChanged, false);
});

test("已保存跨岗位目标：crossJob 为真且展示目标标题；空草稿不改已保存目标", () => {
  const state = growthTargetJobState(baseTask({ targetJobId: NEW_JOB, targetJobTitle: "E2E 岗位C（合成）" }), "");
  assert.equal(state.savedTargetJobId, NEW_JOB);
  assert.equal(state.savedTargetJobTitle, "E2E 岗位C（合成）");
  assert.equal(state.crossJob, true);
  assert.equal(state.effectiveTargetJobId, NEW_JOB);
  assert.equal(state.selectionChanged, false);
});

test("有效 UUID 草稿是未保存改选：不得误示为已保存，生成不使用它", () => {
  const state = growthTargetJobState(baseTask(), OTHER_JOB);
  assert.equal(state.effectiveTargetJobId, OTHER_JOB);
  assert.equal(state.selectionChanged, true);
  assert.equal(state.savedTargetJobId, ORIGINAL);
});

test("草稿含空白会先修剪再校验", () => {
  const state = growthTargetJobState(baseTask(), ` ${OTHER_JOB} `);
  assert.equal(state.effectiveTargetJobId, OTHER_JOB);
  assert.equal(state.selectionChanged, true);
});

test("非 UUID 草稿回落到已保存目标，不作为有效改选", () => {
  for (const draft of ["not-a-uuid", "12345", `${OTHER_JOB}x`]) {
    const state = growthTargetJobState(baseTask(), draft);
    assert.equal(state.effectiveTargetJobId, ORIGINAL);
    assert.equal(state.selectionChanged, false);
  }
});

test("跨岗位任务改选回原岗位同样是未保存改选，必须再保存", () => {
  const state = growthTargetJobState(baseTask({ targetJobId: NEW_JOB, targetJobTitle: "E2E 岗位C（合成）" }), ORIGINAL);
  assert.equal(state.effectiveTargetJobId, ORIGINAL);
  assert.equal(state.selectionChanged, true);
});

test("分析开始后岗位与材料同时锁定；失败后解锁可人工重存", () => {
  assert.equal(growthTargetJobState(baseTask({ status: "analyzing", analysisTaskId: "t" }), "").locked, true);
  assert.equal(growthTargetJobState(baseTask({ status: "compared", analysisTaskId: "t" }), "").locked, true);
  assert.equal(growthTargetJobState(baseTask({ status: "materials_selected", analysisTaskId: null }), "").locked, false);
  assert.equal(growthTargetJobState(baseTask({ status: "analysis_failed", analysisTaskId: "t" }), "").locked, false);
});

test("公开岗位列表参数：空白搜索省略 q，页码下限 1，pageSize 固定 10", () => {
  assert.deepEqual(growthJobListQuery("  ", 0), { page: 1, pageSize: 10 });
  assert.deepEqual(growthJobListQuery(" 岗位 ", 3), { page: 3, pageSize: 10, q: "岗位" });
  assert.equal(Object.hasOwn(growthJobListQuery("", 1), "q"), false);
});

test("分页边界：总页末 hasNext 关闭，翻页不受前 100 条限制", () => {
  assert.deepEqual(growthJobPageBounds(25, 1, 10), { hasPrevious: false, hasNext: true, page: 1 });
  assert.deepEqual(growthJobPageBounds(25, 3, 10), { hasPrevious: true, hasNext: false, page: 3 });
  assert.equal(growthJobPageBounds(250, 24, 10).hasNext, true);
  assert.equal(growthJobPageBounds(250, 25, 10).hasNext, false);
  assert.equal(growthJobPageBounds(250, 0, 10).page, 1);
});

test("背景变化包含 job 标签并翻译为目标岗位变化", () => {
  assert.equal(GROWTH_CHANGES.job, "目标岗位变化");
});

test("保存材料选择：未选目标时请求体不含 targetJobId（client 层对可省略字段的契约）", async () => {
  const original = globalThis.fetch;
  let body = null;
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("/growth-tasks/task-1/materials")) {
      assert.equal(init.method, "PUT");
      body = JSON.parse(init.body);
      return new Response(JSON.stringify({ code: 0, message: "success", data: baseTask(), requestId: "t" }), { headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ code: 404, message: "unexpected", data: null, requestId: "t" }), { status: 404, headers: { "Content-Type": "application/json" } });
  };
  try {
    await api.growthMaterials("task-1", { resumeVersionId: "r1", projectVersionIds: [] });
    assert.deepEqual(Object.keys(body).sort(), ["projectVersionIds", "resumeVersionId"]);
  } finally { globalThis.fetch = original; }
});

test("保存材料选择：已选目标时请求体携带 targetJobId UUID", async () => {
  const original = globalThis.fetch;
  let body = null;
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("/growth-tasks/task-1/materials")) {
      body = JSON.parse(init.body);
      return new Response(JSON.stringify({ code: 0, message: "success", data: baseTask({ targetJobId: NEW_JOB, targetJobTitle: "E2E 岗位C（合成）" }), requestId: "t" }), { headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ code: 404, message: "unexpected", data: null, requestId: "t" }), { status: 404, headers: { "Content-Type": "application/json" } });
  };
  try {
    await api.growthMaterials("task-1", { resumeVersionId: "r1", projectVersionIds: [], targetJobId: NEW_JOB });
    assert.equal(body.targetJobId, NEW_JOB);
  } finally { globalThis.fetch = original; }
});

test("保存载荷：组件实际路径恒携带显式目标——清除改选=保持已保存跨岗位目标，而非省略回原岗位", () => {
  const task = baseTask({ targetJobId: NEW_JOB, targetJobTitle: "E2E 岗位C（合成）" });
  const payload = growthSaveMaterialsPayload(task, "", { resumeVersionId: "r1", projectVersionIds: ["p1"] });
  assert.equal(payload.targetJobId, NEW_JOB);
  assert.deepEqual(Object.keys(payload).sort(), ["projectVersionIds", "resumeVersionId", "targetJobId"]);
});

test("保存载荷：明确选择原岗位并保存，请求体显式携带原岗位 UUID", () => {
  const task = baseTask({ targetJobId: NEW_JOB, targetJobTitle: "E2E 岗位C（合成）" });
  const payload = growthSaveMaterialsPayload(task, ORIGINAL, { resumeVersionId: "r1", projectVersionIds: [] });
  assert.equal(payload.targetJobId, ORIGINAL);
});

test("保存载荷：旧任务无草稿=显式原岗位；有效改选草稿=使用改选", () => {
  assert.equal(growthSaveMaterialsPayload(baseTask(), "", { resumeVersionId: "r1", projectVersionIds: [] }).targetJobId, ORIGINAL);
  assert.equal(growthSaveMaterialsPayload(baseTask(), OTHER_JOB, { resumeVersionId: "r1", projectVersionIds: [] }).targetJobId, OTHER_JOB);
});

test("保存载荷经真实 client 发送：清除改选场景 body 携带已保存目标", async () => {
  const original = globalThis.fetch;
  let body = null;
  const task = baseTask({ targetJobId: NEW_JOB, targetJobTitle: "E2E 岗位C（合成）" });
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("/growth-tasks/task-1/materials")) {
      body = JSON.parse(init.body);
      return new Response(JSON.stringify({ code: 0, message: "success", data: task, requestId: "t" }), { headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ code: 404, message: "unexpected", data: null, requestId: "t" }), { status: 404, headers: { "Content-Type": "application/json" } });
  };
  try {
    const materials = growthSaveMaterialsPayload(task, "", { resumeVersionId: "r1", projectVersionIds: [] });
    await api.growthMaterials("task-1", materials);
    assert.equal(body.targetJobId, NEW_JOB);
  } finally { globalThis.fetch = original; }
});

// 时间线行为模型：镜像 GrowthWorkspace 的真实接线——私有任务 guard 与公开
// 列表 jobGuard 分离；两个 finally 都以各自 guard 判定收尾；隐藏/刷新同时
// 清除两者与列表 busy。断言对象是请求交错后的 UI 状态，不只是孤立 guard。
function componentModel() {
  const taskGuard = createGrowthRequestGuard();
  const jobGuard = createGrowthRequestGuard();
  const state = { task: null, busy: false, jobItems: [], jobBusy: false, jobError: "" };
  return {
    taskGuard, jobGuard, state,
    async perform(operation) {
      const ticket = taskGuard.start(); state.busy = true;
      try { const value = await operation(); if (taskGuard.accepts(ticket)) state.task = value; }
      finally { if (taskGuard.accepts(ticket)) state.busy = false; }
    },
    async loadJobs(operation) {
      const ticket = jobGuard.start(); state.jobBusy = true;
      try { const list = await operation(); if (jobGuard.accepts(ticket)) state.jobItems = list.items; }
      catch (reason) { if (jobGuard.accepts(ticket)) state.jobError = String(reason); }
      finally { if (jobGuard.accepts(ticket)) state.jobBusy = false; }
    },
    hide() {
      taskGuard.clear(); jobGuard.clear();
      state.task = null; state.jobItems = []; state.jobBusy = false; state.jobError = ""; state.busy = false;
    },
    refresh() {
      taskGuard.start(); jobGuard.clear();
      state.jobItems = []; state.jobBusy = false; state.jobError = "";
    },
  };
}

const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

test("时间线：保存进行中读取列表——两个回执都生效，列表 busy 正常收尾不卡死", async () => {
  const model = componentModel();
  const slowSave = deferred(), slowList = deferred();
  const savePromise = model.perform(async () => { await slowSave.promise; return { id: "saved" }; });
  const listPromise = model.loadJobs(async () => { await slowList.promise; return { items: ["job-1"] }; });
  slowSave.resolve("saved"); slowList.resolve(null);
  await Promise.all([savePromise, listPromise]);
  assert.deepEqual(model.state.task, { id: "saved" });
  assert.deepEqual(model.state.jobItems, ["job-1"]);
  assert.equal(model.state.busy, false);
  assert.equal(model.state.jobBusy, false);
  assert.equal(model.state.jobError, "");
});

test("时间线：列表读取进行中保存——保存回执不被列表废弃", async () => {
  const model = componentModel();
  const slowList = deferred();
  const listPromise = model.loadJobs(async () => { await slowList.promise; return { items: ["job-2"] }; });
  await model.perform(async () => ({ id: "saved-after-list" }));
  assert.deepEqual(model.state.task, { id: "saved-after-list" });
  assert.equal(model.state.busy, false);
  slowList.resolve(null);
  await listPromise;
  assert.deepEqual(model.state.jobItems, ["job-2"]);
  assert.equal(model.state.jobBusy, false);
});

test("时间线：隐藏页后过期的列表与任务回执都不得复活状态", async () => {
  const model = componentModel();
  const slowSave = deferred(), slowList = deferred();
  const savePromise = model.perform(async () => { await slowSave.promise; return { id: "ghost" }; });
  const listPromise = model.loadJobs(async () => { await slowList.promise; return { items: ["ghost-job"] }; });
  model.hide();
  slowSave.resolve("ghost"); slowList.resolve(null);
  await Promise.all([savePromise, listPromise]);
  assert.equal(model.state.task, null);
  assert.deepEqual(model.state.jobItems, []);
  assert.equal(model.state.jobBusy, false);
  assert.equal(model.state.busy, false);
});

test("时间线：手动刷新清除在途列表并复位列表 busy，新列表随后生效", async () => {
  const model = componentModel();
  const slowList = deferred();
  const staleList = model.loadJobs(async () => { await slowList.promise; return { items: ["stale"] }; });
  model.refresh();
  slowList.resolve(null);
  await staleList;
  assert.deepEqual(model.state.jobItems, []);
  assert.equal(model.state.jobBusy, false);
  await model.loadJobs(async () => ({ items: ["fresh"] }));
  assert.deepEqual(model.state.jobItems, ["fresh"]);
  assert.equal(model.state.jobBusy, false);
});

test("时间线：更新请求使旧列表作废时，busy 仍由收尾路径复位", async () => {
  const model = componentModel();
  const slowFirst = deferred(), fastSecond = deferred();
  const first = model.loadJobs(async () => { await slowFirst.promise; return { items: ["old"] }; });
  const second = model.loadJobs(async () => { await fastSecond.promise; return { items: ["new"] }; });
  fastSecond.resolve(null); slowFirst.resolve(null);
  await Promise.all([first, second]);
  assert.deepEqual(model.state.jobItems, ["new"]);
  assert.equal(model.state.jobBusy, false);
});
