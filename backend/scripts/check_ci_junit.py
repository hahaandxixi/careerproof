"""CI JUnit gate for the mandatory PostgreSQL strict test set (goal 49).

Verifies that the strict modules really executed and passed by reading the
pytest JUnit XML, never by trusting the pytest exit code alone. Requirements:

* every expected module contributes at least one testcase;
* no testcase reports failure, error or skipped;
* ``test_attempt_hard_stop`` covers the full two-chain four-window matrix
  (verification/matching x send_intent_committed/response_observed/
  receipt_committed/ledger_committed) with every window actually passing.

Checks are ordered so the first failing category decides the exit code:
0 all green, 2 missing JUnit file, 3 format error, 4 empty XML,
5 module missing, 6 hard-stop window missing, 7 failure/error/skipped.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

STRICT_MODULES = (
    "test_ai_budget_production_race",
    "test_durable_matching",
    "test_attempt_hard_stop",
    "test_visual_postgres_concurrency",
    "test_mcp_postgres_isolation",
    "test_real_matching",
    "test_durable_attempt_service",
    "test_ai_request_attempt_migration",
    "test_knowledge_semantic_postgres",
    "test_ai_shared_budget_service",
    "test_ai_shared_budget_migration",
    "test_application_reconsent_migration",
    "test_data_integrity_migration",
    "test_refresh_atomicity",
    "test_login_rate_limit",
    "test_login_limit_migration",
)
HARD_STOP_MODULE = "test_attempt_hard_stop"
HARD_STOP_FUNCTION = "test_real_child_hard_stop_then_database_only_recovery"
HARD_STOP_PHASES = (
    "send_intent_committed",
    "response_observed",
    "receipt_committed",
    "ledger_committed",
)
HARD_STOP_CHAINS = ("verification", "matching")
NOT_PASSED_TAGS = ("failure", "error", "skipped")

EXIT_PASS = 0
EXIT_MISSING_FILE = 2
EXIT_FORMAT = 3
EXIT_EMPTY = 4
EXIT_MODULE_MISSING = 5
EXIT_WINDOW_MISSING = 6
EXIT_NOT_PASSED = 7


def fail(exit_code: int, reason: str) -> int:
    print(f"CI-JUNIT-GATE result=FAIL category={exit_code} reason={reason}")
    return exit_code


def collect_testcases(junit_paths: list[str]):
    """Parse every JUnit file and return (module, name, bad-tag) triples.

    A bad tag is the first failure/error/skipped child, or "" when the case
    passed. Raises ValueError with a category-3 message on format problems.
    """
    collected = []
    for path in junit_paths:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as error:
            raise ValueError(f"{path} is not parseable XML: {error}") from error
        if root.tag not in ("testsuite", "testsuites"):
            raise ValueError(f"{path} root element <{root.tag}> is not a JUnit suite")
        for node in root.iter("testcase"):
            name = node.get("name")
            classname = node.get("classname", "")
            if not name:
                raise ValueError(f"{path} has a testcase without a name attribute")
            bad = next(
                (tag for tag in NOT_PASSED_TAGS if node.find(tag) is not None), ""
            )
            collected.append((classname, name, bad))
    return collected


def module_of(classname: str) -> str:
    """Map a dotted classname like app.tests.test_real_matching to its stem."""
    normalized = classname.replace("/", ".").rstrip(".")
    return normalized.rsplit(".", 1)[-1] if "." in normalized else normalized


def hardstop_windows(names: list[str]) -> set[tuple[str, str]]:
    """Extract the (phase, chain) pairs present in parametrised case names."""
    windows: set[tuple[str, str]] = set()
    for name in names:
        function, separator, parameters = name.partition("[")
        if (function != HARD_STOP_FUNCTION or not separator
                or not parameters.endswith("]")):
            continue
        tokens = parameters[:-1].split("-")
        if len(tokens) != 2:
            continue
        parts = set(tokens)
        for phase in HARD_STOP_PHASES:
            for chain in HARD_STOP_CHAINS:
                if parts == {phase, chain}:
                    windows.add((phase, chain))
    return windows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "junit", nargs="+",
        help="pytest --junitxml output files for the strict PostgreSQL set",
    )
    args = parser.parse_args(argv)

    absent = [path for path in args.junit if not Path(path).is_file()]
    if absent:
        return fail(EXIT_MISSING_FILE, f"JUnit file(s) missing: {', '.join(absent)}")

    try:
        collected = collect_testcases(args.junit)
    except ValueError as error:
        return fail(EXIT_FORMAT, str(error))

    if not collected:
        return fail(EXIT_EMPTY, f"no testcases found in: {', '.join(args.junit)}")

    grouped: dict[str, list[tuple[str, str]]] = {}
    for classname, name, bad in collected:
        grouped.setdefault(module_of(classname), []).append((name, bad))

    missing = [module for module in STRICT_MODULES if module not in grouped]
    if missing:
        return fail(EXIT_MODULE_MISSING, f"module(s) without any testcase: "
                                         f"{', '.join(missing)}")

    hardstop_names = [name for name, _ in grouped.get(HARD_STOP_MODULE, [])]
    expected_windows = {
        (phase, chain)
        for phase in HARD_STOP_PHASES
        for chain in HARD_STOP_CHAINS
    }
    missing_windows = sorted(expected_windows - hardstop_windows(hardstop_names))
    if missing_windows:
        detail = ", ".join(f"{phase}-{chain}" for phase, chain in missing_windows)
        return fail(EXIT_WINDOW_MISSING,
                    f"{HARD_STOP_MODULE} missing window(s): {detail}")

    not_passed = [
        f"{module}::{name} ({bad})"
        for module, cases in grouped.items()
        for name, bad in cases
        if bad
    ]
    if not_passed:
        return fail(EXIT_NOT_PASSED,
                    f"testcase(s) not actually passed: {'; '.join(not_passed)}")

    print(f"CI-JUNIT-GATE result=PASS modules={len(STRICT_MODULES)} "
          f"testcases={len(collected)} hardstop_windows={len(expected_windows)}")
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
