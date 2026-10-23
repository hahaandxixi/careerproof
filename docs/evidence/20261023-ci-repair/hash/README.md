# Agent offline packet checkout repair (2026-10-23)

Base: 5a6b9c821c9e7de1cc79b90f7e35a93142e74148. Owned worktree codex/ci-hash-fix. Windows Python 3.12.14, pytest 9.0.3.

Only `.gitattributes`, the current offline-only fixture and a focused smoke regression test changed. Six previously reviewed sources already use explicit LF. The two additional policy/budget paths had no eol policy; Windows core.autocrlf=true produced CRLF, while Git blobs and Linux checkout use LF. The original fixture matches exactly those CRLF bytes; byte-baseline.json records Git/LF/CRLF hashes for all eight sources. Source text equals Git blob after CRLF-to-LF only. No production source, authorization guard, historical preflight, live output, claim or budget changed. The two current offline hashes now equal the accepted Git blobs.

Reproduction: converted only these two checked-out files to Git LF bytes, then ran the two smoke suites. red-final.raw.out/red-linux.xml preserve 13 failed / 12 passed, exit 1, with complete nodeids and tracebacks. The final-log-write test KeyError guard is secondary: smoke.main rejects source before constructing a guard; its test-only finally then accesses missing holder. This does not occur after restoring exact reviewed-byte identity, and production error handling was not changed.

Commands (cwd this worktree/backend; APP_ENV=test AI_EXTERNAL_ENABLED=false AI_PROVIDER=mock DATABASE_URL=sqlite:///./.tmp-hash-isolated.db PYTHONPATH=backend absolute):

- python -m pytest app/tests/test_agent_evidence_smoke.py app/tests/test_agent_smoke_hard_stop.py --basetemp=.tmp/hash-red-approved --junitxml=../docs/evidence/20261023-ci-repair/hash/red-linux.xml -> exit 1, 13 failed / 12 passed.
- Same targets with --basetemp=.tmp/hash-green --junitxml=../docs/evidence/20261023-ci-repair/hash/green.xml -> exit 0, 27 passed / 0 failed / 0 skipped, 1.73s.
- python -m ruff check app/tests/test_agent_evidence_smoke.py -> exit 0.
- git -c core.autocrlf=true/false checkout-index --force --prefix=<owned isolated prefix>/ -- <eight paths> -> both exit 0; all 16 hashes match packet and all eight files are LF. checkout-matrix.json records actual results; this simulates Git checkout settings on Windows, not an actual Linux execution.

The two new mutation cases exercise the real byte-hash guard: accepted copied policy/budget passes, adding actual content fails. Existing MockTransport-only tests now reach missing usage, request reservation/physical cap, provider retry, source mismatch, receipt write failure and HTTP400/401 planning/analysis stops. No network model call and no business DB access.

Local execution note: initial sandbox runs were interrupted after asyncio made no progress; one earlier local --basetemp attempt lacked its parent .tmp. These partial raw logs are preserved and are not acceptance. Approved scoped rerun completed in 1.73s. Linux full CI remains the integrator responsibility.
