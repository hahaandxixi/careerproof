import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { transform } = require("sucrase");
registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith(".ts")) {
      return {
        format: "module",
        source: transform(readFileSync(fileURLToPath(url), "utf8"), {
          transforms: ["typescript"], filePath: url,
        }).code,
        shortCircuit: true,
      };
    }
    return nextLoad(url, context);
  },
});

const { displayFilePath, displayFilePathText } = await import(
  pathToFileURL(fileURLToPath(new URL("../src/lib/display-path.ts", import.meta.url))).href
);
const UUID = "6db170c9-ea2b-4036-84d1-47260c687014";

test("strips only the leading material UUID", () => {
  assert.equal(displayFilePath(`${UUID}/README.md`), "README.md");
  assert.equal(displayFilePath(`${UUID}/tests/test_registration.py`), "tests/test_registration.py");
});

test("returns a path without a prefix unchanged", () => {
  assert.equal(displayFilePath("runtime/pytest-output.txt"), "runtime/pytest-output.txt");
});

test("only strips the first segment when the path has multiple slashes", () => {
  assert.equal(displayFilePath(`${UUID}/campus_signup/api.py`), "campus_signup/api.py");
});

test("removes UUID prefixes embedded in saved explanatory text", () => {
  assert.equal(
    displayFilePathText(`规则层另有未发送材料：${UUID}/README.md:1-9。`),
    "规则层另有未发送材料：README.md:1-9。",
  );
});
