import { test } from "node:test";
import assert from "node:assert/strict";
import config from "../next.config.mjs";

test("all frontend and proxied paths receive baseline response headers", async () => {
  const [rule] = await config.headers();
  assert.equal(rule.source, "/:path*");
  const headers = Object.fromEntries(rule.headers.map(h => [h.key.toLowerCase(), h.value]));
  assert.equal(headers["x-frame-options"], "DENY");
  assert.equal(headers["x-content-type-options"], "nosniff");
  assert.equal(headers["referrer-policy"], "strict-origin-when-cross-origin");
  assert.equal((await config.rewrites())[0].source, "/backend/:path*");
});

test("HSTS requires both production and explicit HTTPS deployment", async () => {
  const original = { mode: process.env.NODE_ENV, https: process.env.CAREERPROOF_HTTPS };
  try {
    for (const [mode, https, enabled] of [
      ["development", "true", false], ["production", "false", false],
      ["production", undefined, false], ["production", "true", true],
    ]) {
      process.env.NODE_ENV = mode;
      if (https === undefined) delete process.env.CAREERPROOF_HTTPS;
      else process.env.CAREERPROOF_HTTPS = https;
      const header = (await config.headers())[0].headers.find(h => h.key === "Strict-Transport-Security");
      assert.equal(Boolean(header), enabled, `${mode}/${https}`);
      if (enabled) assert.equal(header.value, "max-age=31536000");
    }
  } finally {
    for (const [key, value] of [["NODE_ENV", original.mode], ["CAREERPROOF_HTTPS", original.https]]) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});
