import test from "node:test";
import assert from "node:assert/strict";
import { retryTaskHref } from "../src/lib/task-navigation.ts";

test("retry into a new task keeps the original report comparison context", () => {
  const original = "11111111-1111-1111-1111-111111111111";
  const next = "22222222-2222-2222-2222-222222222222";
  assert.equal(retryTaskHref(original, next, original), `/tasks/${next}?compareTo=${original}`);
  assert.equal(retryTaskHref(original, next, original, next), `/tasks/${next}?compareTo=${original}&sourceRequirement=${next}`);
  assert.equal(retryTaskHref(original, next), `/tasks/${next}`);
  assert.equal(retryTaskHref(original, original, original), null, "same-task retry preserves the current route");
});
