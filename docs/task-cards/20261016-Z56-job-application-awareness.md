# 传智杯56 · ZCode · 岗位页已有投递提示

Baseline: main a45b345; actual Git root `D:/jbcode/web ai/jianli`.
Owner: ZCode only writes `jianli/src/components/JobDetailView.tsx`, a small new `jianli/src/lib/job-application-status.ts`, related tests named `job-application-status*.test.mjs`, and `docs/evidence/20261016-Z56-job-application-awareness/`. Codex owns all other files and final integration. No other agent may edit your files until handoff.

## Observed obstacle
Normal-site video walkthrough generated a new report, then application submission correctly refused to replace an existing active application. The job matching form only shows a generic applications link. Students cannot see the existing submission status before generating another report.

## Deliverable
- In the STUDENT job matching form, read the existing authenticated `api.myApplications()` separately from material loading. Display the matching job's real active application status and link to `/applications#application-<id>`.
- Reuse actual shared application status wording; stay with slate/indigo and compact layout.
- Only show a concrete status when a returned record proves it. Missing/incomplete/error data never means “not applied”. Loading/error/unknown are explicit, retry is read-only, and a failed status read must not prevent matching.
- Withdrawn history must not be presented as active or restore consent. No automatic withdrawal/reapplication, no prechecked consent, no blocking valid new report generation. The server remains authoritative.
- Protect against response-after-unmount, route/job/identity switches and stale responses. Clear previous user's data immediately. Recheck on explicit retry / normal return-to-page if appropriate; avoid polling loops.
- Do not couple status errors to material reset or make extra model requests. Preserve existing selected-version/query behavior and model consent defaults.

## Verification and stop
First write focused synthetic failing cases proving the actual defect/new contract, then implementation and related regressions. Include same-job vs other-job, active vs withdrawn, failed read, out-of-order/identity or unmount behavior, preserved materials and no model/write action from retry. Exercise the real controller/component when practical, not only constants or source regex.
Use installed Node22 and existing `backend/.tmp/refresh-ui-20261015` dependency runtime only after first copying it into your OWN `backend/.tmp/z56-ui-20261016` stage; do not modify or run commands in Codex's stage or live `dep-frontend-20261010`. Do not copy private files. If permissions fail, retain results and report; never change ACL or integrity.
Store exact commands and full raw outputs (each failure separate), self-review, source hashes and concise handoff in the evidence directory. Tests/typecheck permitted in owned stage. No installing dependencies. No browser claim without actual browser evidence. Do not restart/stop/build in served directories or touch services, databases, .env, credentials, storage, client DB, website model calls, external messages, P2 stash, Git commit/push, cleanup or other sources.
Stop after this bounded delivery; report changed files, confirmed tests, remaining risks in one screen. Codex will review and activate.

## Dispatch
2026-10-16: live ZCode quota panel showed personal 5-hour 100%, weekly 100% (Oct 23), MCP 100% (Oct 17). Dispatched under jbcode as 传智杯56, GLM-5.3 / highest; observed working state and initial Git verification. Implementation and activation are not yet accepted.


## Independent review / budget correction (2026-10-16)
ZCode first delivery is terminal: 18 targeted, 303 frontend and typecheck reported; not yet accepted or activated. Codex found over-strong withdrawn wording and missing return-to-page refresh. The next narrow fix must not restart repository research or repeat all tests. User requested difficulty-based effort; live menu only offers low/high/highest. Selected GLM-5.3 LOW for any next turn; no follow-up was sent because native focus moved to another foreground app. Current observed quota: weekly 92%, five-hour 60%. This is a snapshot, not precise per-action billing attribution. Codex may implement remaining review corrections after this terminal handoff.
