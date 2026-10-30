import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import {
  MATERIAL_ACCEPT, materialFileError, materialFileSize, materialFileType,
  pickMaterialFile, latestMaterialVersions, materialSelectionChanged, materialVersionTime,
  uploadedMaterialFromQuery, growthUploadReturnHref,
} from "../src/lib/material-upload.ts";

test("browser suffix and byte contract matches the backend including uppercase images", () => {
  const allowed = ["pdf", "docx", "txt", "png", "jpg", "jpeg", "webp", "bmp"];
  for (const kind of ["resume", "project"]) {
    assert.deepEqual(MATERIAL_ACCEPT[kind].split(","), (kind === "project" ? ["zip", ...allowed] : allowed).map(ext => `.${ext}`));
    for (const ext of allowed) {
      assert.equal(materialFileError(kind, { name: `proof.${ext.toUpperCase()}`, size: 10 * 1024 * 1024 }), "");
      assert.match(materialFileError(kind, { name: `proof.${ext}`, size: 10 * 1024 * 1024 + 1 }), /10MB/);
    }
    for (const name of ["bad.exe", "bad.png.exe", "no-extension", "bad.", "bad.svg", "bad.gif"]) assert.match(materialFileError(kind, { name, size: 1 }), /格式不支持/);
  }
  assert.match(materialFileError("resume", { name: "proof.ZIP", size: 1 }), /格式不支持/);
  assert.equal(materialFileError("project", { name: "proof.ZIP", size: 30 * 1024 * 1024 }), "");
  assert.match(materialFileError("project", { name: "proof.zip", size: 30 * 1024 * 1024 + 1 }), /30MB/);
});

test("same-name projects keep separate latest roles and histories by stable identity",()=>{
 const rows=[{kind:"project",resourceId:"reference",versionNumber:1,materialRole:"portfolio"},{kind:"project",resourceId:"reference",versionNumber:2,materialRole:"reference"},{kind:"project",resourceId:"personal",versionNumber:1,materialRole:"portfolio"}];
 const latest=latestMaterialVersions(rows);
 assert.equal(latest.find(r=>r.resourceId==="reference").materialRole,"reference");
 assert.equal(latest.find(r=>r.resourceId==="personal").materialRole,"portfolio");
 assert.equal(rows.length,3);
});

test("only valid source timestamps are displayed; missing history never becomes now", () => {
  assert.equal(materialVersionTime(), null);
  assert.equal(materialVersionTime(""), null);
  assert.equal(materialVersionTime("not-a-date"), null);
  assert.match(materialVersionTime("2026-10-22T08:15:00+08:00"), /2026/);
});

test("single file selection rejects multiple files without choosing an arbitrary first one", () => {
  const a = new File(["a"], "A.JPG"); const b = new File(["b"], "B.JPG");
  assert.deepEqual(pickMaterialFile("resume", [a]), { file: a, error: "" });
  assert.equal(pickMaterialFile("resume", [a, b]).file, null);
  assert.match(pickMaterialFile("resume", [a, b]).error, /每次请选择一个/);
  assert.equal(pickMaterialFile("resume", []).file, null);
  assert.match(materialFileType(a), /JPG.*未提供 MIME/);
  assert.equal(materialFileSize(1024), "1.0 KB");
  assert.equal(materialFileSize(2 * 1024 * 1024), "2.0 MB");
});

test("latest upload summaries keep independent resume/project identities and pending newest versions", () => {
  const rows = [{ kind: "project", resourceId: "same", versionNumber: 1 }, { kind: "resume", resourceId: "same", versionNumber: 1 }, { kind: "project", resourceId: "same", versionNumber: 3, status: "pending" }, { kind: "project", resourceId: "same", versionNumber: 2 }];
  const frozen = structuredClone(rows);
  assert.deepEqual(latestMaterialVersions(rows).map(row => [row.kind, row.versionNumber]), [["project", 3], ["resume", 1]]);
  assert.deepEqual(rows, frozen);
});

test("proposed material versions are compared against server-saved identities, not filenames/order", () => {
  const saved = [{ kind: "resume", id: "r1" }, { kind: "project", id: "p1" }, { kind: "project", id: "p2" }];
  assert.equal(materialSelectionChanged(saved, "r1", ["p2", "p1"]), false);
  assert.equal(materialSelectionChanged(saved, "r1", ["p2", "p3"]), true);
  assert.equal(materialSelectionChanged(saved, "r2", ["p1", "p2"]), true);
  assert.equal(materialSelectionChanged([], "r1", []), true);
  assert.equal(materialSelectionChanged([], "", []), false);
});

test("returned upload uses only a validated hint and does not encode selection/save actions", () => {
  const versionId = "22222222-2222-2222-2222-222222222222";
  const value = { kind: "project", versionId };
  assert.deepEqual(uploadedMaterialFromQuery(new URLSearchParams({ uploadedKind: "project", uploadedVersion: versionId })), value);
  assert.equal(uploadedMaterialFromQuery(new URLSearchParams({ uploadedKind: "company", uploadedVersion: versionId })), null);
  assert.equal(uploadedMaterialFromQuery(new URLSearchParams({ uploadedKind: "resume", uploadedVersion: "../../foreign" })), null);
  assert.equal(growthUploadReturnHref("owned-task", value), `/growth/owned-task?uploadedKind=project&uploadedVersion=${versionId}`);
  assert.equal(growthUploadReturnHref("owned-task"), "/growth/owned-task");
});

const require = createRequire(import.meta.url);
const { transform } = require("sucrase");
const runtime = require("react/jsx-runtime");
const contract = await import("../src/lib/material-upload.ts");
function loadComponent(path, modules) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const code = transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  return mod.exports;
}
function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (Array.isArray(node)) return node.map(value => find(value, predicate)).find(Boolean);
  return predicate(node) ? node : find(node.props?.children, predicate);
}

test("real dropzone shares chooser/drop validation and retains a native keyboard file input", () => {
  const component = loadComponent("../src/components/MaterialFileDropzone.tsx", {
    react: { useState: value => [value, () => {}] }, "react/jsx-runtime": runtime, "@/lib/material-upload": contract,
  }).default;
  const changes = []; const errors = [];
  const tree = component({ id: "proof", kind: "project", file: null, target: "报名服务 · 新版本", onChange: value => changes.push(value), onError: value => errors.push(value) });
  const input = find(tree, node => node.type === "input");
  assert.equal(input.props.type, "file"); assert.equal(input.props.disabled, false);
  assert.equal(input.props["aria-describedby"], "proof-help proof-selected");
  assert.equal(input.props.required, undefined); // dropping must not be blocked by an empty native FileList
  const file = new File(["pixels"], "proof.WEBP", { type: "image/webp" });
  input.props.onChange({ target: { files: [file] } }); assert.equal(changes.at(-1), file);
  let prevented = 0;
  tree.props.onDrop({ preventDefault() { prevented++; }, dataTransfer: { files: [file] } });
  assert.equal(prevented, 1); assert.equal(changes.at(-1), file);
  tree.props.onDrop({ preventDefault() {}, dataTransfer: { files: [file, file] } });
  assert.equal(changes.at(-1), null); assert.match(errors.at(-1), /每次请选择一个/);
  const disabled = component({ id: "proof", kind: "project", file: null, target: "报名服务", disabled: true, onChange() { assert.fail("disabled drop must not select"); }, onError() { assert.fail("disabled drop must not change errors"); } });
  disabled.props.onDrop({ preventDefault() {}, dataTransfer: { files: [file] } });
});

test("real returned-version review highlights only current owned data and never selects or saves", () => {
  const versionId = "22222222-2222-2222-2222-222222222222";
  let calls = 0;
  const projectPicker = () => null; const resumePicker = () => null;
  const review = loadComponent("../src/components/GrowthUploadReturn.tsx", {
    "react/jsx-runtime": runtime,
    "next/link": { __esModule: true, default: props => runtime.jsx("a", props) },
    "next/navigation": { useSearchParams: () => new URLSearchParams({ uploadedKind: "project", uploadedVersion: versionId }) },
    "@/lib/material-upload": contract,
    "./ResumeVersionPicker": { __esModule: true, default: resumePicker },
    "./ProjectVersionPicker": { __esModule: true, default: projectPicker },
  }).GrowthMaterialReview;
  const projects = [{ id: "p", name: "报名服务", versions: [{ id: versionId, versionNumber: 2, originalFilename: "service.zip", status: "completed", createdAt: "2026-10-22T08:15:00+08:00" }] }];
  const props = { resumes: [], projects, resumeId: "", projectIds: [], onResumeChange() { calls++; }, onProjectsChange() { calls++; } };
  const tree = review(props);
  const picker = find(tree, node => node.type === projectPicker);
  assert.deepEqual(picker.props.selectedIds, []);
  assert.equal(picker.props.highlightedVersionId, versionId);
  const { renderToStaticMarkup } = require("react-dom/server");
  assert.match(renderToStaticMarkup(tree), /第 2 版.*service.zip.*尚未加入当前选择/);
  assert.match(renderToStaticMarkup(tree), /<time dateTime="2026-10-22T08:15:00\+08:00">上传于 .*2026/);
  const foreign = review({ ...props, projects: [] });
  assert.equal(find(foreign, node => node.type === projectPicker).props.highlightedVersionId, undefined);
  assert.match(renderToStaticMarkup(foreign), /尚未在当前账号材料列表中找到/);
  assert.equal(calls, 0);
});

test("actual project picker highlights a returned version without selecting it or marking search results newest", async () => {
  const pickerLogic = await import("../src/lib/material-picker.ts");
  const projects = [{ id: "p", name: "作品", versions: [
    { id: "old", versionNumber: 1, status: "completed", originalFilename: "old.zip" },
    { id: "new", versionNumber: 2, status: "completed", originalFilename: "new.zip", createdAt: "2026-10-22T08:15:00+08:00" },
  ] }];
  function picker(query, selectedIds = []) {
    let index = 0;
    const component = loadComponent("../src/components/ProjectVersionPicker.tsx", {
      react: { useState: value => [index++ === 0 ? query : value, () => {}] },
      "react/jsx-runtime": runtime, "next/link": { __esModule: true, default: props => runtime.jsx("a", props) },
      "@/lib/material-upload": contract, "@/lib/material-picker": pickerLogic, "@/app/demo/samples.json": { __esModule: true, default: [] },
    }).default;
    return component({ projects, selectedIds, onChange() { assert.fail("render must not select"); }, highlightedVersionId: "new" });
  }
  const { renderToStaticMarkup } = require("react-dom/server");
  const tree = picker("");
  assert.equal(find(tree, node => node.type === "details").props.open, true);
  const html = renderToStaticMarkup(tree);
  assert.match(html, /第 2 版.*最新可用版本.*刚上传.*尚未选择/);
  assert.doesNotMatch(html, /checked=""/);
  assert.match(html, /已解析.*<time dateTime="2026-10-22T08:15:00\+08:00">上传于 .*2026/);
  assert.doesNotMatch(renderToStaticMarkup(picker("old.zip")), /最新可用版本/);
  const selected = renderToStaticMarkup(picker("", ["new"]));
  assert.equal((selected.match(/<time dateTime="2026-10-22T08:15:00\+08:00">/g) || []).length, 2, "selected summary and selectable row both retain actual upload time");
});
