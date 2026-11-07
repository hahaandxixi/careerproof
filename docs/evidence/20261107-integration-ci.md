# 2026-11-07 integration PR #13 CI checkpoint

## Baseline CI on 044ee43

- Workflow CI run: 42344045795, workflow "CI"
- Windows offline contracts: run 42344045788, **success**
- Frontend: **17 failures**
- SQLite backend: **17 failures**
- PostgreSQL backend: **1 failure**
- PR: draft #13, base main 1e1e75a, head 044ee43

## Failure groups and fixes

### Frontend: application-board-visibility / component stubs

- 10 application-board-visibility failures were transformed component stubs missing
  the newly imported comparable-group functions and a fixture without
  `fixedRequirementBasisComplete`.
- Added the real comparable helpers to the stub and a complete comparable fixture.
- Remaining report/reading failures came from updated production copy/markup and
  test harness event stubs:
  - Flow section navigation needed an event with `preventDefault` and a
    `navigateEvidenceFragment` stub.
  - Source wrap labels are now `换行：开/关`; reading assertions follow that visible
    label while keeping wrap-state and copy-byte assertions.
  - Archive success copy is now `已移出材料库`, with the same destructive/manual
    recovery assertions.
  - Action-panel headings now reflect saved requirements; plan copy asserts the
    actual deliverable still rendered.
  - Source identity extraction accepts both wrap modes while still proving the
    exact physical line content.

### Backend: reviewed source

- `Agent reviewed source changed` was caused by real candidate changes in
  `evidence_workflow.py` and `contracts.py`.
- Reviewed source hashes in
  `backend/app/tests/fixtures/current-20261022/agent-offline-input.json` were refreshed
  after reviewing the merged source. Historical packet hash and tamper-rejection
  tests remain intact.

### Backend: report history/pagination returned 0

- Product ownership correctly uses `candidate_ref == str(User.id)`.
- Test fixtures were still writing `StudentProfile.id` into `candidate_ref`, so the
  product-history filter returned zero.
- Updated the report-history and pagination test fixtures to the User identity;
  `source_scope` now accepts both the new User-id form and legacy profile-id form.
- No product query/business rule was weakened.

## Final CI on 7799a1a

- CI run 42365437939: **success**
  - frontend: success
  - backend-unit (full SQLite): success
  - backend-postgres: success
- Windows offline contracts run 42365437943: **success**
- PR #13 head: `7799a1aa554720365d3d9840a808e9c45cdaa5ce`
- No test skips, deleted assertions, or tamper-check weakening were used.

## Local verification after fixes

- Frontend full suite: **711/711 passed**
- Previously failing backend targets: `test_fixture_read_policy`, two
  `test_real_matching` cases, `test_runtime_report_identity`, report-history and
  pagination targets: **7 passed**
- Full SQLite local run before the final fixture corrections: 1733 passed, 4 failed;
  those 4 were the fixture/ownership cases fixed above.
- No live 3140 acceptance yet.
