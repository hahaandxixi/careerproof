"""Reverse tests for the CI JUnit gate (goal 49): every failure category exits
non-zero and only a complete green strict run exits zero.

The gate script is executed exactly the way the CI workflow invokes it, as a
subprocess on synthesised JUnit XML documents, so these tests need no database
and no network. The contract below (exit codes, module list, hard-stop window
matrix) is deliberately restated here instead of imported from the script: the
tests must stay red when the script drifts, not follow it.
"""

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = BACKEND_ROOT / "scripts" / "check_ci_junit.py"

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
)
HARD_STOP_MODULE = "test_attempt_hard_stop"
HARD_STOP_PHASES = (
    "send_intent_committed",
    "response_observed",
    "receipt_committed",
    "ledger_committed",
)
HARD_STOP_CHAINS = ("verification", "matching")

EXIT_PASS = 0
EXIT_MISSING_FILE = 2
EXIT_FORMAT = 3
EXIT_EMPTY = 4
EXIT_MODULE_MISSING = 5
EXIT_WINDOW_MISSING = 6
EXIT_NOT_PASSED = 7


def hardstop_case_names():
    return [
        f"test_real_child_hard_stop_then_database_only_recovery[{phase}-{chain}]"
        for chain in HARD_STOP_CHAINS
        for phase in HARD_STOP_PHASES
    ]


def build_junit(cases):
    """Render a pytest-style testsuite; each case is (module, name, status)."""
    suite = ET.Element(
        "testsuite",
        {"name": "ci-synthetic", "tests": str(len(cases)), "failures": "0",
         "errors": "0", "skipped": "0"},
    )
    for module, name, status in cases:
        node = ET.SubElement(
            suite, "testcase",
            {"classname": f"app.tests.{module}", "name": name, "time": "0.01"},
        )
        if status != "passed":
            ET.SubElement(node, status, {"message": f"synthetic {status}"})
    return ET.tostring(suite, encoding="unicode")


def green_cases(hardstop_names=None):
    """A fully passing strict run: every module present, hard-stop 8/8."""
    cases = []
    for module in STRICT_MODULES:
        if module == HARD_STOP_MODULE:
            names = hardstop_names or hardstop_case_names()
        else:
            names = ["test_sample_green"]
        cases.extend((module, name, "passed") for name in names)
    return cases


def run_gate(tmp_path, documents):
    """Write each document as a JUnit file and invoke the gate once."""
    paths = []
    for index, text in enumerate(documents):
        path = tmp_path / f"junit-{index}.xml"
        path.write_text(text, encoding="utf-8")
        paths.append(str(path))
    return subprocess.run(
        [sys.executable, str(GATE_SCRIPT), *paths],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_gate_script_exists():
    assert GATE_SCRIPT.is_file(), f"missing gate script: {GATE_SCRIPT}"


def test_green_strict_run_exits_zero(tmp_path):
    result = run_gate(tmp_path, [build_junit(green_cases())])
    assert result.returncode == EXIT_PASS, result.stdout + result.stderr


def test_same_parameters_on_unrelated_function_do_not_prove_hard_stops(tmp_path):
    names = [name.replace('test_real_child_hard_stop_then_database_only_recovery',
                          'test_unrelated_helper') for name in hardstop_case_names()]
    result = run_gate(tmp_path, [build_junit(green_cases(names))])
    assert result.returncode == EXIT_WINDOW_MISSING, result.stdout + result.stderr


def test_repeated_parameter_tokens_do_not_prove_the_exact_matrix(tmp_path):
    names = [name[:-1] + '-' + name[:-1].rsplit('-', 1)[-1] + ']'
             for name in hardstop_case_names()]
    result = run_gate(tmp_path, [build_junit(green_cases(names))])
    assert result.returncode == EXIT_WINDOW_MISSING, result.stdout + result.stderr


def test_split_junit_files_still_exits_zero(tmp_path):
    """CI feeds the strict file and the hard-stop file to one gate call."""
    rest = [case for case in green_cases() if case[0] != HARD_STOP_MODULE]
    hardstop = [
        (module, name, status)
        for module, name, status in green_cases()
        if module == HARD_STOP_MODULE
    ]
    result = run_gate(
        tmp_path, [build_junit(rest), build_junit(hardstop)]
    )
    assert result.returncode == EXIT_PASS, result.stdout + result.stderr


def test_extra_unknown_module_does_not_fail(tmp_path):
    cases = green_cases() + [("test_ci_junit_gate", "test_sample", "passed")]
    result = run_gate(tmp_path, [build_junit(cases)])
    assert result.returncode == EXIT_PASS, result.stdout + result.stderr


def test_missing_junit_file_exits_nonzero(tmp_path):
    absent = tmp_path / "junit-absent.xml"
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), str(absent)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == EXIT_MISSING_FILE, result.stdout + result.stderr
    assert "junit-absent.xml" in result.stdout + result.stderr


def test_malformed_xml_exits_nonzero(tmp_path):
    result = run_gate(tmp_path, ["<testsuite><testcase not-xml"])
    assert result.returncode == EXIT_FORMAT, result.stdout + result.stderr


def test_unexpected_root_element_exits_nonzero(tmp_path):
    result = run_gate(tmp_path, ["<result><case/></result>"])
    assert result.returncode == EXIT_FORMAT, result.stdout + result.stderr


def test_testcase_without_name_attribute_exits_nonzero(tmp_path):
    broken = (
        '<testsuite name="s" tests="1">'
        '<testcase classname="app.tests.test_real_matching"/></testsuite>'
    )
    result = run_gate(tmp_path, [broken])
    assert result.returncode == EXIT_FORMAT, result.stdout + result.stderr


def test_empty_testsuite_exits_nonzero(tmp_path):
    result = run_gate(
        tmp_path, ['<testsuite name="s" tests="0" failures="0" errors="0"/>']
    )
    assert result.returncode == EXIT_EMPTY, result.stdout + result.stderr


def test_missing_module_exits_nonzero(tmp_path):
    cases = [case for case in green_cases() if case[0] != "test_real_matching"]
    result = run_gate(tmp_path, [build_junit(cases)])
    assert result.returncode == EXIT_MODULE_MISSING, result.stdout + result.stderr
    assert "test_real_matching" in result.stdout + result.stderr


def test_module_without_cases_in_second_file_exits_nonzero(tmp_path):
    """A module claimed by neither JUnit file must fail even if one file is green."""
    rest = [case for case in green_cases() if case[0] not in
            (HARD_STOP_MODULE, "test_mcp_postgres_isolation")]
    result = run_gate(tmp_path, [build_junit(rest)])
    assert result.returncode == EXIT_MODULE_MISSING, result.stdout + result.stderr


@pytest.mark.parametrize("dropped_phase,dropped_chain", [
    ("ledger_committed", "matching"),
    ("send_intent_committed", "verification"),
])
def test_missing_hardstop_window_exits_nonzero(
        tmp_path, dropped_phase, dropped_chain):
    names = [
        name for name in hardstop_case_names()
        if f"[{dropped_phase}-{dropped_chain}]" not in name
    ]
    result = run_gate(tmp_path, [build_junit(green_cases(names))])
    assert result.returncode == EXIT_WINDOW_MISSING, result.stdout + result.stderr
    assert dropped_phase in result.stdout + result.stderr
    assert dropped_chain in result.stdout + result.stderr


def test_hardstop_without_parametrised_names_exits_nonzero(tmp_path):
    """One flat case name cannot stand in for the two-chain four-window matrix."""
    cases = green_cases(hardstop_names=["test_only_one_flat_case"])
    result = run_gate(tmp_path, [build_junit(cases)])
    assert result.returncode == EXIT_WINDOW_MISSING, result.stdout + result.stderr


@pytest.mark.parametrize("status", ["failure", "error", "skipped"])
def test_not_passed_case_exits_nonzero(tmp_path, status):
    cases = green_cases()
    cases.append(("test_real_matching", "test_synthetic_bad", status))
    result = run_gate(tmp_path, [build_junit(cases)])
    assert result.returncode == EXIT_NOT_PASSED, result.stdout + result.stderr
    assert "test_synthetic_bad" in result.stdout + result.stderr


def test_skipped_hardstop_window_exits_nonzero(tmp_path):
    """A skipped window counts as not actually passed even though it is present."""
    cases = [
        (module, name, "skipped" if name.endswith("[receipt_committed-matching]")
         else status)
        for module, name, status in green_cases()
    ]
    result = run_gate(tmp_path, [build_junit(cases)])
    assert result.returncode == EXIT_NOT_PASSED, result.stdout + result.stderr
