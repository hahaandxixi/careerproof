import { test } from "node:test";
import assert from "node:assert/strict";
import { filterResumeMaterials, resumeDisplayCategory } from "../src/lib/resume-picker.ts";

const demoTitles = ["CP08｜数据库 DBA｜测试简历"];
const version = (id, number, filename, status = "completed") => ({ id, versionNumber: number, originalFilename: filename, status });
const resumes = [
  { id: "own", title: "测试1", versions: [version("own1", 1, "我的简历.docx")] },
  { id: "demo", title: demoTitles[0], versions: [version("d1", 1, "CP08-简历-v1.txt"), version("d2", 2, "CP08-简历-v2.txt"), version("pending", 3, "future.txt", "running")] },
  { id: "old", title: "AI完整报告合成简历20260917-130215", versions: [version("old1", 1, "student-resume.txt")] },
  { id: "failed", title: "失败简历", versions: [version("f1", 1, null, "failed")] },
];

test("known fixture categories change display only; unknown user titles stay visible", () => {
  assert.equal(resumeDisplayCategory(demoTitles[0], demoTitles), "demo");
  for (const title of ["数据库工程师 DBA验收简历0917", "自动化运维工程师验收简历0917", "历史难例合成简历", "历史验收简历 20260926-142342", "Function Calling 合成简历 20260918-152713", "AI完整报告合成简历20260918-140714", "浏览器全链路简历-20260918", "OCR合成烟测-20260917", "开源归属回归：Flask QA 合成简历"]) {
    assert.equal(resumeDisplayCategory(title, demoTitles), "history");
  }
  for (const title of ["测试1", "AI 开发工程师简历", "我的 Function Calling 项目", "CP08｜我自己的简历", "AI完整报告合成简历"]) {
    assert.equal(resumeDisplayCategory(title, demoTitles), "personal");
  }
});

test("default list omits known old fixtures and unfinished versions without modifying source", () => {
  const original = structuredClone(resumes);
  const rows = filterResumeMaterials(resumes, "", false, demoTitles);
  assert.deepEqual(rows.map(row => row.id), ["own", "demo"]);
  assert.deepEqual(rows[1].versions.map(v => v.id), ["d2", "d1"]);
  assert.deepEqual(resumes, original);
});

test("search can discover hidden history and version filenames, including null filenames", () => {
  assert.equal(filterResumeMaterials(resumes, " STUDENT-RESUME.TXT ", false, demoTitles)[0].category, "history");
  assert.deepEqual(filterResumeMaterials(resumes, "CP08-简历-v1", false, demoTitles)[0].versions.map(v => v.id), ["d1"]);
  assert.deepEqual(filterResumeMaterials(resumes, "第 2 版", false, demoTitles)[0].versions.map(v => v.id), ["d2"]);
  assert.deepEqual(filterResumeMaterials(resumes, "not found", false, demoTitles), []);
  assert.equal(filterResumeMaterials([{ id: "null", title: "无文件名", versions: [version("n1", 1, null)] }], "无文件名", false, demoTitles).length, 1);
});

test("all completed history stays available for existing explicit links even when search hides it", () => {
  const selectedId = "old1";
  assert.equal(filterResumeMaterials(resumes, "", false, demoTitles).some(r => r.versions.some(v => v.id === selectedId)), false);
  const all = filterResumeMaterials(resumes, "", true, demoTitles);
  assert.equal(all.find(r => r.versions.some(v => v.id === selectedId))?.id, "old");
  assert.deepEqual(all.map(row => row.id), ["own", "demo", "old"]);
  assert.equal(selectedId, "old1");
});
