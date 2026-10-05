// Validate all path-derived inputs before the runner performs any filesystem I/O.
export const ENTERPRISE_SCENARIOS = Object.freeze([
  "skeleton", "reply-failure", "notification-filter", "late-response",
  "download-withdraw", "withdraw-verify", "viewport390",
]);

export function parseRunnerArgs(args) {
  const values = { "--run": "audit-20261005", "--scenario": "skeleton" };
  const seen = new Set();
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i], value = args[i + 1];
    if (!Object.hasOwn(values, key) || seen.has(key) || !value || value.startsWith("--")) {
      throw new Error("Invalid runner arguments");
    }
    seen.add(key);
    values[key] = value;
  }
  // This is the same run-id format enforced by Start/Stop-E2E and the seeder.
  if (!/^[a-z0-9][a-z0-9-]{0,31}$/.test(values["--run"]) ||
      !ENTERPRISE_SCENARIOS.includes(values["--scenario"])) {
    throw new Error("Invalid runner arguments");
  }
  return { runId: values["--run"], scenario: values["--scenario"] };
}

// JSON parser messages can contain source fragments on some Node versions.
// Credential failures must never reuse their original message or cause.
export function parseCredentialDocument(text) {
  let value;
  try { value = JSON.parse(text); }
  catch { throw new Error("Invalid synthetic credential document"); }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid synthetic credential document");
  }
  return value;
}

export function withdrawnNotificationStatus(outcome) {
  if (outcome === "unavailable-notice") return "pass";
  if (outcome === "REPORT-STILL-READABLE") return "fail";
  return "blocked"; // Missing notice/report cannot prove withdrawn authorization.
}

export function prepareEvidenceRecord(step, n, secrets, at) {
  const entry = { n, at, ...step };
  if (entry.detail !== undefined) {
    entry.detail = String(entry.detail);
    for (const secret of secrets) {
      if (secret) entry.detail = entry.detail.split(secret).join("<redacted>");
    }
  }
  const line = `[${entry.n}] ${entry.status ?? "info"} ${entry.name}${entry.detail ? " :: " + entry.detail : ""}`;
  return { entry, line };
}

export function withdrawnOpenCardsStatus(proof) {
  if (proof.openAnchors.includes(`#application-${proof.withdrawnId}`)) return "fail";
  const allLanded = proof.openCount > 0 && proof.openAnchors.length === proof.openCount &&
    proof.openAnchors.every(anchor => /^#application-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(anchor));
  return proof.inaccessibleCount >= 2 && proof.withdrawalEventFound &&
    proof.olderUnavailableCount >= 1 && allLanded ? "pass" : "blocked";
}
