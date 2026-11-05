"""Regression proof for test_parser_release_double.py.

Runs the same release test with the production parser's PDF context management removed.
The shared working tree is never modified:

  1. a temporary copy of ``document_parser.py`` is written with the ``with`` block removed;
  2. a ``conftest.py`` in that temp rootdir swaps ``sys.modules['app.tools.document_parser']``
     for the broken copy *before* the test module is imported;
  3. every other ``app.*`` module still comes from the real backend, so the test failure
     can only be caused by the removed context management.

Expected: the broken run fails on the ``exit`` assertions. The real source passes
(``test_parser_release_double.py``, 3 passed).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PARSER = REPO / "backend" / "app" / "tools" / "document_parser.py"
TEST = Path(__file__).resolve().parent / "test_parser_release_double.py"
PYTHON = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
WORKDIR = REPO / "backend" / ".tmp" / "t71-copybreak"

ORIGINAL = '        try:\n            with fitz.open(path) as document:'
BROKEN = '        try:\n            document = fitz.open(path)\n            if True:'

CONFTEST = '''\
"""Temp rootdir conftest: import the broken parser copy instead of the real one."""
import importlib.util
import sys
from pathlib import Path

_broken = Path(__file__).with_name("broken_parser.py")
_spec = importlib.util.spec_from_file_location("app.tools.document_parser", _broken)
_module = importlib.util.module_from_spec(_spec)
sys.modules["app.tools.document_parser"] = _module
_spec.loader.exec_module(_module)
'''


def main() -> int:
    source = PARSER.read_text(encoding="utf-8")
    if ORIGINAL not in source:
        print("FAIL: anchor for the PDF context manager not found")
        return 1
    broken = source.replace(ORIGINAL, BROKEN, 1)

    WORKDIR.mkdir(parents=True, exist_ok=True)
    (WORKDIR / "broken_parser.py").write_text(broken, encoding="utf-8")
    (WORKDIR / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    test_copy = WORKDIR / "test_parser_release_double.py"
    test_copy.write_text(TEST.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"broken copy: {WORKDIR / 'broken_parser.py'}")
    print(f"real source untouched: {PARSER}")

    basetemp = REPO / "backend" / ".tmp" / "t71-copybreak-basetemp"
    command = [
        str(PYTHON),
        "-m",
        "pytest",
        str(test_copy),
        "-q",
        "--no-header",
        f"--basetemp={basetemp}",
        "-p",
        "no:cacheprovider",
        "--tb=line",
        "-rA",
    ]
    print("run:", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=str(REPO / "backend"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout = completed.stdout
    print(stdout)
    if completed.stderr.strip():
        print("STDERR (tail):", completed.stderr[-1200:])

    real_failure = "AssertionError" in stdout and "failed" in stdout
    print(f"broken-copy exit code: {completed.returncode}")
    print(f"assertion failure observed: {real_failure}")
    if real_failure and completed.returncode != 0:
        print("RESULT: PASS (broken copy fails on the release assertions)")
        return 0
    print("RESULT: FAIL (broken copy did not fail for the intended reason)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
