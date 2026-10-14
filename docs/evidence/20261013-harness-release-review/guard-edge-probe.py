"""Pure-module probes for the release-smoke / seed-e2e isolation guards.

No database, no HTTP request, no service start: only pure guard functions and
local files under a temporary directory. Companion evidence for
docs/evidence/20261013-harness-release-review/review.md.

Run from anywhere with the backend venv interpreter:
    python guard-edge-probe.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve()
BACKEND = HERE.parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

from evals.release_smoke import smoke_account, validate_run  # noqa: E402
from evals.seed_e2e import (  # noqa: E402
    IsolationError,
    guard_base_url,
    guard_database_url,
    guard_run_id,
    verify_startup_manifest,
)

FAILURES: list[str] = []


def note(label: str, text: str) -> None:
    print(f"[OBS] {label}: {text}")


def check(label: str, ok: bool, text: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{': ' + text if text else ''}")
    if not ok:
        FAILURES.append(label)


def make_link(target: Path, link: Path) -> str:
    """Create a directory link without elevation when possible; report its kind."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except OSError as exc:
        print(f"  (os.symlink unavailable: {exc.__class__.__name__})")
    import _winapi

    last: Exception | None = None
    for first, second in ((target, link), (link, target)):
        try:
            _winapi.CreateJunction(str(first), str(second))
        except OSError as exc:  # noqa: PERF203
            last = exc
            continue
        if link.exists():
            return "junction"
    raise OSError(f"neither symlink nor junction could be created: {last}")


def probe_environment() -> None:
    print("=" * 78)
    print("ENVIRONMENT")
    print("=" * 78)
    print(f"python={sys.version.split()[0]} platform={sys.platform}")
    print(f"backend={BACKEND}")
    print(f"Path.is_symlink exists={hasattr(Path, 'is_symlink')}")
    print(f"Path.is_junction exists={hasattr(Path, 'is_junction')}")


def probe_database_url_port() -> None:
    print("=" * 78)
    print("PROBE 1  guard_database_url: is the PostgreSQL port pinned to 5432?")
    print("=" * 78)
    for url in (
        "postgresql+asyncpg://u:p@127.0.0.1:5432/cp_e2e_probe",
        "postgresql+asyncpg://u:p@127.0.0.1:6543/cp_e2e_probe",
        "postgresql+asyncpg://u:p@localhost/cp_e2e_probe",
    ):
        try:
            note("accepted", f"{url} -> database {guard_database_url(url)!r}")
        except IsolationError as exc:
            note("refused", f"{url} -> {exc}")


def probe_base_url_port() -> None:
    print("=" * 78)
    print("PROBE 2  guard_base_url: the API port IS pinned to 8001")
    print("=" * 78)
    for url in ("http://127.0.0.1:8001/api/v1", "http://127.0.0.1:8000/api/v1"):
        try:
            note("accepted", f"{url} -> {guard_base_url(url)!r}")
        except IsolationError as exc:
            note("refused", f"{url} -> {exc}")


def probe_run_id() -> None:
    print("=" * 78)
    print("PROBE 3  guard_run_id edge values")
    print("=" * 78)
    for rid in ("probe", "probe-", "probe--x", "a" * 32, "a" * 33):
        try:
            guard_run_id(rid)
            note("accepted", f"run id {rid!r}")
        except IsolationError as exc:
            note("refused", f"run id {rid!r} -> {exc}")


def probe_seed_manifest_flags(tmp: Path) -> None:
    print("=" * 78)
    print("PROBE 4  verify_startup_manifest (the guard seed_e2e's CLI calls)")
    print("=" * 78)
    run = "probe"
    started = datetime.now(UTC)
    storage = tmp / "manifest-flags" / ".tmp/e2e-storage" / run
    storage.mkdir(parents=True, exist_ok=True)
    manifest = {
        "runId": run,
        "databaseName": f"cp_e2e_{run}",
        "backendPort": 8001,
        "aiExternalEnabled": "false",
        "aiProvider": "mock",
        "storageDir": str(storage),
        # Deliberately the real app entry point and no synthetic-verification flag:
        "backendTarget": "app.main:app",
        "syntheticVerification": False,
        "backend": {"id": 123, "startedAt": started.isoformat()},
    }
    try:
        verify_startup_manifest(
            manifest,
            run_id=run,
            database_name=f"cp_e2e_{run}",
            storage_dir=storage,
            process_probe=lambda _: started,
        )
        note(
            "accepted",
            "backendTarget='app.main:app' + syntheticVerification=False passed "
            "verify_startup_manifest (release_smoke.validate_run checks both; "
            "seed_e2e.py:284-293 does not)",
        )
    except IsolationError as exc:
        note("refused", f"unexpected: {exc}")


def probe_junction_smoke_account(tmp: Path) -> None:
    print("=" * 78)
    print("PROBE 5  smoke_account through a linked .tmp/release-smoke")
    print("=" * 78)
    root = tmp / "junction-smoke" / "root"
    outside = tmp / "junction-smoke" / "outside"
    (root / ".tmp").mkdir(parents=True, exist_ok=True)
    outside.mkdir(parents=True, exist_ok=True)
    try:
        kind = make_link(outside, root / ".tmp/release-smoke")
    except OSError as exc:
        note("skipped", f"could not create any link: {exc}")
        return
    link = root / ".tmp/release-smoke"
    note("link kind", kind)
    note("Path.is_symlink()", str(link.is_symlink()))
    if hasattr(Path, "is_junction"):
        note("Path.is_junction()", str(link.is_junction()))
    note("any(parent.is_symlink())", str(any(p.is_symlink() for p in link.parents)))
    try:
        account = smoke_account(root, "probe")
    except ValueError as exc:
        check(f"smoke_account refused a {kind} link", exc.args[0] == "Linked smoke state is refused", str(exc))
        return
    landed = outside / "probe.credentials.json"
    escaped = landed.exists()
    password = json.loads(landed.read_text(encoding="utf-8"))["password"] if escaped else ""
    check(
        f"smoke_account refused a {kind} link",
        False,
        f"NOT refused: wrote {landed} outside root; password_len={len(password)} "
        f"matches returned={password == account['password']}",
    )
    check(
        "credentials file stayed inside the repository root",
        not escaped,
        f"landed={landed}",
    )


def probe_junction_validate_run(tmp: Path) -> None:
    print("=" * 78)
    print("PROBE 6  validate_run with .tmp/e2e and .tmp/e2e-run behind links")
    print("=" * 78)
    run = "probe"
    root = tmp / "junction-validate" / "root"
    (root / ".tmp").mkdir(parents=True, exist_ok=True)
    state = tmp / "junction-validate" / "state"
    manifest_dir = tmp / "junction-validate" / "manifest"
    state.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    (state / f"{run}.json").write_text(
        json.dumps({"runId": run, "apiBaseUrl": "http://127.0.0.1:8001/api/v1/"}),
        encoding="utf-8",
    )
    (manifest_dir / f"processes-{run}.json").write_text(
        json.dumps(
            {
                "runId": run,
                "backendPort": 8001,
                "frontendPort": 3001,
                "databaseName": f"cp_e2e_{run}",
                "aiProvider": "mock",
                "aiExternalEnabled": "false",
                "syntheticVerification": True,
                "backendTarget": "evals.e2e_verification:create_app --factory",
                "storageDir": str(root / ".tmp/e2e-storage" / run),
                "backend": {"id": 123, "startedAt": started.isoformat()},
            }
        ),
        encoding="utf-8",
    )
    kinds = []
    try:
        kinds.append(("e2e", make_link(state, root / ".tmp/e2e")))
        kinds.append(("e2e-run", make_link(manifest_dir, root / ".tmp/e2e-run")))
    except OSError as exc:
        note("skipped", f"could not create links: {exc}")
        return
    note("link kinds", str(kinds))
    note(
        "is_symlink()",
        str({name: (root / ".tmp" / name).is_symlink() for name, _ in kinds}),
    )
    try:
        validate_run(root, run, process_probe=lambda _: started)
    except ValueError as exc:
        check(
            "validate_run refused the linked state as linked",
            "Linked E2E state is refused" in str(exc),
            f"raised {exc!r} instead",
        )
        return
    check(
        "validate_run refused the linked state as linked",
        False,
        "ACCEPTED: both state files were read through links and validation passed",
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="harness46-probe-"))
    print(f"tempdir={tmp}")
    try:
        probe_environment()
        probe_database_url_port()
        probe_base_url_port()
        probe_run_id()
        probe_seed_manifest_flags(tmp)
        probe_junction_smoke_account(tmp)
        probe_junction_validate_run(tmp)
    finally:
        print("=" * 78)
        print(f"FINDING_LABELS={FAILURES}")
        print("These [FAIL] lines are guard observations, not test-suite failures.")
        print("=" * 78)
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
