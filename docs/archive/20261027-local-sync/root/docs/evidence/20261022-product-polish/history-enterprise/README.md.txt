# Report history, applications and enterprise comparison

2026-10-22. Base commit `01232d27e8768121592b6c05300e0b5ba5170a55`; accepted patch files and SHA-256 are in `accepted-files.json`. No Git commits, service operations, installs or real AI requests were made by this task.

## User-facing changes

- Reports can be found by frozen job title across the student's entire authorized history, or narrowed to exact job ID using the same-job button. Window metadata counts the complete owned job history before optional search/pagination. Latest/later labels are displayed only from recorded server metadata. Fixed material titles, versions and short IDs are available per report.
- My applications can be filtered across all pages by job/company plus all/waiting/enterprise-replied/withdrawn. Enterprise reply and existing next action remain together. Enterprise-replied means an explicit reply exists, not an unread flag or a new duty to respond.
- Enterprise keyword/status/requirement/verdict conditions now precede count and paging. Requirement and verdict must match the same saved item. Keywords search candidate name or decoded saved summary/requirement title/skill/explanation fields; SQL wildcard characters are escaped. Raw JSON serialization and source snippets are not the keyword search contract. Existing enterprise membership, consent and withdrawal restrictions remain.
- My jobs receive current-page batched application counts and pending-reply counts (one grouped aggregate, no per-job request/query). Public jobs do not receive enterprise counts. Job pagination clamps after removal.
- Enterprise matrix keeps the requirement column and header sticky, permits 2–4 authorized current-page candidates to be compared, and displays the selected cell's frozen explanation and up to two exact source excerpts immediately below the matrix. Requirement/version mismatches retain their warning and cannot become a score ranking. Full report, audited open/download, consent and reply flow remain in place.
- An opened report excluded by a server filter can be retained only after fresh permissioned detail lookup. Revocation, tab hiding and late responses still clear protected snapshots. Filtering does not silently destroy an unsent draft. Student job discovery links to the existing career-recommendation route.

## Checks performed

Backend (Python 3.12 from `.venv-dependency23`, external AI disabled):

```text
pytest app/tests/test_product_history_filters.py app/tests/test_z57_pagination.py -q -p no:cacheprovider --basetemp=.tmp/product-history-filters
11 passed; backend-first.raw.out

CAREERPROOF_TEST_DATABASE_URL=postgresql+asyncpg://ci:ci@127.0.0.1:55445/cp_ci
pytest app/tests/test_product_history_filters_postgres.py -q -p no:cacheprovider --basetemp=.tmp/product-history-pg
3 passed; backend-pg.raw.out
```

The PG fixture creates/drops only random `cp_test_<uuid>` schemas; it verifies schema ownership. It does not connect to normal 5432 or the root's cloned product DB. Cases use actual ASGI endpoints/repositories, 43 reports/27 applications/28 candidates, other owner/membership denial, literal `100%_` search, same-item JSON conditions, window ranks, frozen versions and page clamping.

Ruff on all seven changed backend production files plus the two new test modules: exit 0. The first static run found import ordering and formatting issues in the new test, corrected before freezing.

Accepted stage (Node v22.23.1; existing node_modules junction, no installation):

```text
node --test tests/history-enterprise.test.mjs tests/application-board-session.test.mjs tests/application-list.test.mjs tests/application-comparison.test.mjs tests/failure-reply-draft.test.mjs
35 passed; frontend-stage-final.raw.out
node node_modules/typescript/bin/tsc --noEmit
exit 0; typecheck.raw.out
node node_modules/eslint/bin/eslint.js src/components/ReportList.tsx src/components/ApplicationList.tsx src/components/ApplicationBoard.tsx src/components/JobList.tsx src/lib/application-board-session.ts src/lib/api/client.ts src/lib/api/domain.ts tests/history-enterprise.test.mjs tests/application-board-session.test.mjs
exit 0; lint.raw.out
```

`frontend-stage.raw.out` preserves one obsolete page-only wording assertion failure. The expectation was changed to global-job scope; behavior/permission assertions remain. `frontend-first.raw.out` additionally contains 43 passing targeted checks in the full dirty workspace; it is not the accepted-stage result.

## Accepted patch isolation

Backend, API types/client and report/job lists were clean at baseline. ApplicationList and ApplicationBoard contained older unaccepted display helpers/wrapping/material summaries. Normalized-LF three-way merge applied only this task's delta onto HEAD in `backend/.tmp/product-polish-20261022/source`. Two touching ApplicationList hunks and one matrix/header hunk required manual resolution. The accepted copy excludes old helper definitions/calls, old wrapping, and the older empty-state redesign; the original workspace keeps them intact. No paused Agent display changes were included. `accepted-files.json` records both stage and workspace hashes rather than claiming they are identical.

## Browser acceptance still assigned to root

Automated rendering tests are server rendering/pure session tests, not pointer/keyboard/browser verification. The root is building and previewing the explicit accepted stage. Cases to verify on desktop and 390px:

1. Reports: a job older than page one is found, same-job button shows all its historical versions, old reports say a later report exists, no unknown history label is invented.
2. Student applications: waiting/replied/withdrawn filters match count/page and reset to page one; enterprise reply links retain the original snapshot.
3. Enterprise: an old candidate is searchable before pagination; combine requirement and verdict; apply a filter excluding the open candidate and verify fresh authorization with draft retained.
4. Compare 2, 3 and 4 candidates; fifth selection is unavailable. Horizontal/vertical matrix scroll keeps row/header identity visible without whole-page overflow.
5. Select a requirement cell: nearby explanation/snippet belongs to that exact candidate and saved requirement; missing requirement gives version-boundary explanation. Reply recipient below remains explicit.
6. Refresh/hide/withdraw while a snapshot/filter request is pending; late data does not restore revoked content. No unprompted sends/downloads occur.

No visual pass, full candidate-version pass, independent first-user acceptance or real model quality conclusion is claimed by this task. Root will record build/browser results separately.


## Independent review follow-up

Three concrete defects were reproduced and minimally corrected before the second handoff:

1. **Stale reply metadata after filtering**: initial regression failed in both fresh-list and exact-detail branches (`filter-metadata-red.raw.out`, 2 failed: selected remained viewed while authoritative row was replied). Filtering now preserves only the immutable report object; status, reply text/kind/references, events and other metadata are replaced from the fresh authorized row/detail. Exact-detail identity and existing generation checks remain. New tests verify both branches, frozen report identity, references and events; previous revocation/late-response cases continue passing.
2. **Focused requirement disappears when results become empty**: the controlled dropdown previously had a nonempty value but no matching option. `RequirementFocusSelect` now retains the selected ID and its already-authorized label when current rows omit it. No broader API read or unrestricted requirement fetch occurs. The rendering regression verifies exact selected ID/label for empty/other-result sets, neutral missing-label fallback and explicit reset to all requirements.
3. **Chinese terms fail against raw JSON text**: the real endpoint returned total=0 for an uploaded Chinese summary (`unicode-red.raw.out`). JSON serialization escapes non-ASCII text, so whole-column cast was an invalid search strategy. Search now decodes known scalar fields: saved summary plus each item's requirementTitle/skill/explanation/aiExplanation, using JSON scalar extraction on SQLite/PostgreSQL. The UI states the exact summary/requirement/explanation scope. A same-case four-term Chinese probe checks summary, requirement title, rule explanation and AI explanation. Source snippets and serialized metadata are not implicitly searched.

Final bounded follow-up results:

- isolated SQLite endpoint module: 3 passed (`unicode-sqlite-green.raw.out`);
- allocated PG random-schema endpoint module: 3 passed (`unicode-pg-green.raw.out`);
- accepted-stage affected frontend/session tests: 38 passed (`filter-stage-green.raw.out`);
- accepted-stage TypeScript and target ESLint: exit 0 (`filter-typecheck.raw.out`, `filter-lint.raw.out`);
- Ruff on changed Python service/tests: all checks passed.

Six accepted files were refreshed: services/applications.py, test_product_history_filters.py, ApplicationBoard.tsx, application-board-session.ts, history-enterprise.test.mjs, application-board-session.test.mjs. The 19-file manifest was refreshed; prior excluded dirty helpers remain excluded. No backend/API/client contract changes beyond the documented decoded keyword implementation. Preview8113 still needs root-owned restart to load the service fix; browser verification/build are root work. This task did not restart it.


## Exact one-candidate browser fixture preparation

Root requested one additional authorized student for the same campus job. The script `backend/.tmp/product-polish-20261022/comparison-candidate.py` verified the accepted config import path, DB `127.0.0.1:55445/cp_product_polish_20261022`, dedicated storage, `AI_EXTERNAL_ENABLED=false`, and the two immutable input SHA-256 values before HTTP writes. Root-owned listener PID489148 and its uvicorn8113 command were read separately; no service was restarted here.

Through existing real API endpoints only, it registered exactly one synthetic student, uploaded the immutable resume and v2-runtime project ZIP, waited for actual parsing/scanning, generated a rules-only report, and explicitly authorized one application with `shareConsent=true`.

- Synthetic display name: 林禾（界面对照合成）.
- User/candidate: `621c39fb-dd5e-40bc-b5d4-8ad75550f8d2`.
- Job: `33d0b1e1-1b45-4ef9-a0fc-c44da1ba1fd0`.
- Report: `2410fd38-bd46-4ff1-8931-278cd71c1a27`.
- Application: `557f6a7a-7409-4f2d-99ac-d1a5a0dd3462`.
- Local-only credentials: `backend/.tmp/product-polish-20261022/comparison-candidate-credentials.json`; passwords/tokens are absent from evidence. `example.invalid` was rejected by the existing EmailStr contract, so root approved a unique documentation-domain `example.com` address. No email was sent.
- Before/after read-only DB facts show exactly two original application snapshot hashes unchanged, exactly one added application (three total), and unchanged AI request-attempt/usage-log counts.
- No enterprise open/download/reply or further candidate was created by this task. Root owns the subsequent browser test.

`comparison-candidate.json` stores config facts, immutable input hashes, request statuses, IDs and before/after snapshot hashes. `comparison-candidate.raw.out` preserves process output. Parsing/scanning completed using the actual API workers; this fixture does not establish model quality or an independent user result.

Final accepted-source affected backend check after Unicode correction: `test_product_history_filters.py` plus `test_z57_pagination.py`, 11 passed in8.47s, `backend-final-stage.raw.out`. No full suite was run here.


## Browser-discovered retained-selection context

The browser confirmed zero matching candidates while an authorized, previously selected report/draft correctly remained open. Its outside-filter notice was accidentally conditional on at least one visible candidate, so zero-result users could mistake the retained report for a matching result. The notice now renders whenever selected ID is outside the page results, including zero rows, and explicitly states which candidate/application remains the reply recipient. No draft, selection, authorization or send behavior was changed. Applied the exact delta to workspace and accepted copy, preserving their separate older changes. Direct notice/session tests: 23 passed; target lint exit0 (`retained-context-tests.raw.out`, `retained-context-lint.raw.out`). Both task and integration accepted-source manifests were refreshed for ApplicationBoard.tsx and failure-reply-draft.test.mjs only. Final browser rebuild/confirmation remains root-owned.


## Selected-cell interpretation validity follow-up (after3dfcef5)

Independent review's suspected invalid-AI display was confirmed by actual SelectedRequirementEvidence rendering: all four new status/fallback cases failed on the previous accepted source (`ai-interpretation-red.raw.out`). Nonempty rejected/invalid AI text and gaps overrode the rule explanation, while valid AI output lacked a source label.

The selected-cell panel now uses AI explanation/gap only when item.aiStatus is validated and report.aiFallbackUsed is false, matching the existing report comparison's validated-item rule plus report/agent fallback boundary. Otherwise it displays item.explanation and evidenceLevelGap. Adopted model explanation is explicitly labelled AI解释; the alternate explanation is labelled 规则解释. Missing AI explanation falls back to the rule field. Original snapshots, sources, levels and scores are unchanged.

Only ApplicationBoard.tsx and history-enterprise.test.mjs changed, applied independently to workspace and accepted source. Four new real-component SSR cases cover invalid_citations, rejected, report fallback with validated item, and valid AI; each asserts the input snapshot is byte-for-byte unchanged after rendering. Full targeted file result:8 passed (`ai-interpretation-green.raw.out`); accepted TypeScript and target ESLint exit0 (`ai-interpretation-typecheck.raw.out`, `ai-interpretation-lint.raw.out`). No full suite, build, service operation, database write or model call. Both accepted manifests were refreshed for these two files only. Parent owns the separate local commit and final page build.


## Complete-details interpretation path closed

The directly related full-report row also selected nonempty AI text without status/fallback validation. Its existing row rendering was moved into SavedRequirementDetail within the same file, used by the actual full-report map, so real SSR covers the production details path rather than a copy of its condition. Four cases reproduced the invalid/rejected/fallback behavior and missing accepted-AI label (`full-interpretation-red.raw.out`).

Both SelectedRequirementEvidence and SavedRequirementDetail now render the same small local SavedRequirementInterpretation component. It is the only direct aiExplanation/aiInformationGap reader remaining in ApplicationBoard.tsx, with the validated && !fallback gate; invalid output uses rule explanation/evidenceLevelGap. Full source snippets, citation identity, material context, line numbers, grades and scores remain intact. The new full-path tests verify frozen-input immutability and unchanged citation/line/snippet/hash display in all four states. Nearby-panel tests remain green.

Final affected rendering and reply-contract files:21 passed (`full-interpretation-green.raw.out`); TypeScript and target ESLint exit0 (`full-interpretation-typecheck.raw.out`, `full-interpretation-lint.raw.out`). Only ApplicationBoard.tsx and history-enterprise.test.mjs changed in workspace and accepted source; both manifests refreshed. No full suite, build, service operations or data writes. Source is frozen for parent review/commit/build.
