import { test } from "node:test";
import assert from "node:assert/strict";
import {
  newProjectAttempt, readAttempt, writeAttempt, submitProjectAttempt,
} from "../src/lib/portfolio-upload.ts";

const file = new File(["test content"], "test.zip");
const project = { id: "project-1", name: "课程项目", description: "说明", version: 1 };
const response = { projectId: project.id, versionId: "v1", taskId: "t1", status: "pending" };

test("failed ZIP upload retains project and request key across repeated retries", async () => {
  let attempt = newProjectAttempt(project.name, project.description);
  const remember = (next) => { attempt = next; };
  let creates = 0;
  const uploadKeys = [];
  const client = {
    async createProject() { creates++; return project; },
    async uploadProjectVersion(id, _file, key) {
      assert.equal(id, project.id);
      assert.equal(attempt.project.id, id); // retained before uploading
      uploadKeys.push(key);
      if (uploadKeys.length < 3) throw new Error("network interrupted");
      return response;
    },
  };
  await assert.rejects(submitProjectAttempt(client, attempt, file, remember));
  await assert.rejects(submitProjectAttempt(client, attempt, file, remember));
  assert.deepEqual(await submitProjectAttempt(client, attempt, file, remember), response);
  assert.equal(creates, 1);
  assert.equal(new Set(uploadKeys).size, 1);
});

test("lost creation response retries with the same creation key", async () => {
  let attempt = newProjectAttempt(project.name, project.description);
  let first = true;
  const createKeys = [];
  const client = {
    async createProject(payload) {
      createKeys.push(payload.requestId);
      if (first) { first = false; throw new Error("response lost after commit"); }
      return project;
    },
    async uploadProjectVersion() { return response; },
  };
  const remember = (next) => { attempt = next; };
  await assert.rejects(submitProjectAttempt(client, attempt, file, remember));
  await submitProjectAttempt(client, attempt, file, remember);
  assert.equal(createKeys.length, 2);
  assert.equal(new Set(createKeys).size, 1);
});

test("refresh restores pending keys for the correct user without storing files", async () => {
  const records = new Map();
  const storage = {
    getItem: (key) => records.get(key) ?? null,
    setItem: (key, value) => records.set(key, value),
    removeItem: (key) => records.delete(key),
  };
  const attempt = newProjectAttempt(project.name, project.description, project);
  writeAttempt(storage, "alice", attempt);
  assert.equal(readAttempt(storage, "bob"), null);
  const restored = readAttempt(storage, "alice");
  assert.deepEqual(restored, attempt);
  assert.equal(JSON.stringify(restored).includes("test content"), false);
  const result = await submitProjectAttempt({
    async createProject() { assert.fail("restored project must not be recreated"); },
    async uploadProjectVersion(id, _file, key) {
      assert.equal(key, attempt.uploadRequestId);
      assert.equal(id, project.id);
      return response;
    },
  }, restored, file, () => {});
  assert.deepEqual(result, response);
  writeAttempt(storage, "alice", null);
  assert.equal(readAttempt(storage, "alice"), null);
});

test("explicit new version retains project but gets a new upload key", () => {
  const first = newProjectAttempt(project.name, project.description, project);
  const second = newProjectAttempt(project.name, project.description, project);
  assert.equal(first.project.id, second.project.id);
  assert.notEqual(first.uploadRequestId, second.uploadRequestId);
});

test("reference role survives upload retry and refresh", async () => {
  const attempt = newProjectAttempt("开源参考", "学习用", project, "reference");
  const stored = new Map();
  const storage = {
    getItem: key => stored.get(key) ?? null,
    setItem: (key, value) => stored.set(key, value),
    removeItem: key => stored.delete(key),
  };
  writeAttempt(storage, "alice", attempt);
  const restored = readAttempt(storage, "alice");
  let sentRole;
  await submitProjectAttempt({
    async createProject() { assert.fail("existing project should be reused"); },
    async uploadProjectVersion(_id, _file, _key, role) { sentRole = role; return response; },
  }, restored, file, () => {});
  assert.equal(sentRole, "reference");
});

test("client timeout keeps the attempt retryable without inferring upload failure", async () => {
  // 超时（AbortError）意味着结果不确定，客户端不得据此推断上传已失败：
  // 服务端可能未收到，也可能已提交。两种情形下客户端的安全反应相同——
  // 保留 attempt、沿用同一 uploadRequestId 重试、不再次创建项目。
  // 若服务端确已提交，重试携带同一幂等键，由后端按 requestId 去重回传
  // 已提交的版本；该去重行为属于后端端点契约，不在本（前端 lib）测试范围。
  let attempt = newProjectAttempt(project.name, project.description);
  const remember = (next) => { attempt = next; };
  let creates = 0;
  const uploadCalls = [];
  const client = {
    async createProject() { creates++; return project; },
    async uploadProjectVersion(id, _file, key) {
      uploadCalls.push({ id, key });
      if (uploadCalls.length === 1) {
        throw new DOMException("The operation was aborted due to timeout", "AbortError");
      }
      // 第二次调用模拟服务端对同一幂等键的响应：无论首次是否已提交，
      // 客户端都接受这一份结果，不做"失败后重发新内容"的推断。
      return response;
    },
  };
  await assert.rejects(submitProjectAttempt(client, attempt, file, remember), /aborted due to timeout/);
  // 结果不确定时 attempt 仍指向已建项目：重试不再走创建，且复用同一上传幂等键。
  assert.equal(attempt.project?.id, project.id);
  assert.deepEqual(await submitProjectAttempt(client, attempt, file, remember), response);
  assert.equal(creates, 1);
  assert.equal(uploadCalls.length, 2);
  assert.equal(uploadCalls[0].key, uploadCalls[1].key);
  assert.ok(uploadCalls.every(call => call.id === project.id));
});
