# 传智杯57 · DeepSeek Harness · 真实列表分页（后端）

Actual Git root D:/jbcode/web ai/jianli, baseline 89d8bed. DeepSeek Flash; use a modest available reasoning level; do not upgrade effort or repeat whole-repo exploration. One bounded delivery, then stop. Codex owns frontend, integration, PostgreSQL verification and commits.

## Ownership
Only backend/app/services/{applications,evidence_growth,analysis}.py, backend/app/api/v1/{applications,evidence_growth,analysis,notifications}.py, a small backend/app/schemas/pagination.py if needed, relevant backend/app/tests/test_*pagination*.py and necessary affected existing backend tests, docs/evidence/20261016-Z57-pagination/. Do not edit common.py or any frontend/client/launcher/provider/accounting file. No other writer will touch your files before terminal handoff.

## Exact API contract (coordinate with Codex frontend)
GET /applications/mine, /jobs/{job_id}/applications, /growth-tasks and /match-reports return data={items,total,page,pageSize}, using existing PaginatedData. Canonical query page>=1, pageSize 1..100 default20 (notifications keeps its existing max50). Clamp page to last available page, empty dataset page1. Stable created_at DESC, id DESC. Count and data use identical ownership/authorization/consent predicates. Preserve every existing authorization/revocation/snapshot check. No migrations or write side effects.

GET /applications/mine additionally accepts optional jobId UUID and applies it within the current student's query, before count/pagination. This supports the job-status hint without loading arbitrary first100 records. No cross-student/cross-enterprise visibility.

Growth historically skips unreadable owned tasks. Keep bounded DB pagination over owned saved rows; total is owned saved-record count. Return explicit unavailableCount for the current page when existing narrow drift exceptions skip a row (small typed GrowthTaskPage extends PaginatedData). Do not misrepresent omitted records as no tasks, broaden catches, or scan/render every historical task to fill a page. Codex frontend will display the count/explanation and use total for navigation.

Notifications: add pageSize canonical query while retaining legacy page_size; preserve existing default20/max50. If both supplied, accept equal values; conflicting values must return422. Do not alter unread/read ownership behavior.

Internal service methods may retain list-return wrappers for existing internal callers/tests if necessary, but HTTP routes must use the explicit paginated methods. Do not introduce a hidden list-all HTTP mode or change unrelated endpoints. Document wrappers and defaults honestly.

## Verification
First focused failing tests, then implement: 101+ owned records and next-page reachability; equal timestamps stable/no duplicate ordering; exact20 last page/clamping/empty; other-owner exclusion; withdrawn enterprise exclusion and manager denial; jobId filtering before pagination; growth skipped-record count; notifications old/new/conflicting query aliases. Use existing isolated SQLite fixtures, own backend/.tmp/z57-pytest-* paths. No normal DB, services, Docker, credentials/.env/client DB, model calls, installs, cleanup, P2, Git commit/push or full-suite reruns. Run targeted and necessarily affected tests + Ruff only. Preserve each failed command/output in a NEW file; never overwrite first failures. If blocked or two failed repair rounds, stop with exact evidence. Handoff source hashes, commands/exits and remaining issues in one screen. No browser or PG success claim without actual evidence.

