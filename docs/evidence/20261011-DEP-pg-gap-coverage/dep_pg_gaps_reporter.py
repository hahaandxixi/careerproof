"""Auxiliary pytest plugin: record per-node outcomes to JSONL.

Loaded only for the 20261011 PG gap-coverage run via `-p dep_pg_gaps_reporter`
with this directory on PYTHONPATH. It only observes reports; it never changes
outcomes, assertions, or skip behavior. Report path comes from the
DEP_PG_GAPS_REPORT environment variable.
"""

import json
import os

_REPORTS = []


def pytest_runtest_logreport(report):
    _REPORTS.append({
        "nodeid": report.nodeid,
        "when": report.when,
        "outcome": report.outcome,
        "skip_reason": (getattr(report.longrepr, "reprcrash", None).message
                        if report.outcome == "skipped" and report.longrepr is not None
                        and getattr(report.longrepr, "reprcrash", None) is not None
                        else None),
    })


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("DEP_PG_GAPS_REPORT")
    if not path:
        return
    # One line per node: prefer the call-phase report; fall back to setup if a
    # node never reached call (fixture-level error/skip).
    best = {}
    for item in _REPORTS:
        current = best.get(item["nodeid"])
        if current is None or (item["when"] == "call" and current["when"] != "call"):
            best[item["nodeid"]] = item
    with open(path, "w", encoding="utf-8") as handle:
        for nodeid in sorted(best):
            handle.write(json.dumps(best[nodeid], ensure_ascii=False) + "\n")
