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
