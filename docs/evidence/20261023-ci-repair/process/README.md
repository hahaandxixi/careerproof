# Hard-stop process relationship repair

Source baseline: `5a6b9c821c9e7de1cc79b90f7e35a93142e74148`.
Original CI run 39877034041, job 120165014116: all eight
`app/tests/test_attempt_hard_stop.py::test_real_child_hard_stop_then_database_only_recovery[verification|matching-send_intent_committed|response_observed|receipt_committed|ledger_committed]`
failed at line 309 before kill/recovery. For verification/send_intent_committed,
expected parent PID 10285, actual 10137. The Linux marker PID is the Popen PID;
its parent is pytest. Windows venv python.exe launches an interpreter child.
Full original CI log is retained by the integration owner at
`backend/.tmp/ci-39877034041-pg.raw.log`.

## Minimal repair

`assert_spawned_worker` verifies the spawned process remains live. If marker PID
matches Popen PID, its actual OS parent must be the spawning pytest process.
Otherwise its actual OS parent must be the Popen launcher. Siblings/unrelated
PIDs and exited launchers are rejected. The existing OS creation timestamp,
nonce, phase, schema, task, attempt, physical HTTP count and ledger predicates
remain unchanged, as do actual kill/wait, lock release and twice-idempotent
DB-only recovery. No production source, skip or xfail changed.

New tests cover both shapes, unrelated/sibling/reused PID relationships, exited
launcher and real process spawning+kill+wait through sys.executable and base
Python. These real Windows processes exercise both direct and launcher shapes;
Linux eight-case execution remains the integration owner's CI responsibility.

## Commands and results

Working directory: this worktree's backend. Python: root repository
`backend/.venv-dependency23/Scripts/python.exe`; no install.

- Red: `python -m pytest app/tests/test_hard_stop_process_identity.py -q --tb=long`
  with the original parent-only assertion extracted into the helper:
  exit 1, 2 failed / 6 passed. The failures are the direct PID shape and real
  base interpreter. `identity-red.raw.out` contains complete tracebacks.
- Windows eight actual stops: `python -m pytest app/tests/test_attempt_hard_stop.py -q --tb=long --basetemp=.tmp-ci-process-hardstop-approved --junitxml=../docs/evidence/20261023-ci-repair/process/windows-hardstop.xml`
  with CAREERPROOF_TEST_DATABASE_URL set only to the assigned local test container:
  exit 0, 8 passed / 0 failed / 0 skipped, 25.05s. Both chains reached each real
  durable phase, actual worker kill/wait, lock release and database recovery.
- Identity and existing worker/resource regression: `python -m pytest app/tests/test_hard_stop_process_identity.py app/tests/test_material_resources.py app/tests/test_worker_identity.py -q --tb=long --basetemp=.tmp-ci-process-resources-approved --junitxml=../docs/evidence/20261023-ci-repair/process/windows-identity-resources.xml`
  exit 0, 35 passed / 0 failed / 0 skipped. This includes ordinary parser exits,
  cancellation cleanup and existing resource safety regressions from this base.
- `python -m ruff check app/tests/test_attempt_hard_stop.py app/tests/test_hard_stop_process_identity.py`:
  exit 0, all checks passed.

Two sandbox invocations stalled without output and were interrupted (exit 1);
the empty raw logs remain. An initial approved resource run used the inaccessible
global pytest temp directory: 17 passed / 18 setup errors, exit 1. Its original
tracebacks remain. Explicit worktree-owned basetemp resolved the environment
failure without changing ACL or tests. No normal DB/service/model was used.

No statement here claims Linux CI, PostgreSQL strict main collection, SQLite
whole-suite, or final integrated HEAD has passed; those belong to root integration.
