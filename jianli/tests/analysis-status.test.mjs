import { test } from "node:test";
import assert from "node:assert/strict";
import { sourceContextVerified, taskUsedExternalAI } from "../src/lib/analysis-status.ts";

test("DeepSeek task steps are shown as successful AI analysis", () => {
  assert.equal(taskUsedExternalAI("deepseek", false), true);
  assert.equal(taskUsedExternalAI("deepseek", undefined), true);
});

test("fallback and local-only steps are not presented as successful AI", () => {
  assert.equal(taskUsedExternalAI("deepseek", true), false);
  assert.equal(taskUsedExternalAI("rules", false), false);
  assert.equal(taskUsedExternalAI(undefined, false), false);
});

test("current source-verified reports are not labeled as unverified history", () => {
  assert.equal(sourceContextVerified("source-context-v2"), true);
  assert.equal(sourceContextVerified("source-context-v4-semantic-documents"), true);
  assert.equal(sourceContextVerified("source-context-v1"), false);
  assert.equal(sourceContextVerified(null), false);
});
