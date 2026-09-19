import { test } from "node:test";
import assert from "node:assert/strict";
import { taskUsedExternalAI } from "../src/lib/analysis-status.ts";

test("DeepSeek task steps are shown as successful AI analysis", () => {
  assert.equal(taskUsedExternalAI("deepseek", false), true);
  assert.equal(taskUsedExternalAI("deepseek", undefined), true);
});

test("fallback and local-only steps are not presented as successful AI", () => {
  assert.equal(taskUsedExternalAI("deepseek", true), false);
  assert.equal(taskUsedExternalAI("rules", false), false);
  assert.equal(taskUsedExternalAI(undefined, false), false);
});
