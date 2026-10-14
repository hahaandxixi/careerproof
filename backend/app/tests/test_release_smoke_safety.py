"""Reject a wrong/demo/business/expired runtime before the smoke chain can write."""

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from evals.release_smoke import prepare_run, smoke_account, validate_run
from evals.seed_e2e import IsolationError


@pytest.fixture
def runtime(tmp_path):
    run = "release-test"
    started = datetime.now(UTC)
    credentials = {"runId": run, "apiBaseUrl": "http://127.0.0.1:8001/api/v1/"}
    manifest = {
        "runId": run,
        "backendPort": 8001,
        "frontendPort": 3001,
        "databaseName": f"cp_e2e_{run}",
        "aiProvider": "mock",
        "aiExternalEnabled": "false",
        "syntheticVerification": True,
        "backendTarget": "evals.e2e_verification:create_app --factory",
        "storageDir": str(tmp_path / ".tmp/e2e-storage" / run),
        "backend": {"id": 123, "startedAt": started.isoformat()},
    }

    def save():
        for subdir, name, value in [
            ("e2e", f"{run}.json", credentials),
            ("e2e-run", f"processes-{run}.json", manifest),
        ]:
            directory = tmp_path / ".tmp" / subdir
            directory.mkdir(parents=True, exist_ok=True)
            (directory / name).write_text(json.dumps(value), encoding="utf-8")

    save()
    return tmp_path, run, started, credentials, manifest, save


@pytest.mark.parametrize(
    "field,value",
    [
        ("databaseName", "careerproof"),
        ("aiExternalEnabled", "true"),
        ("aiProvider", "deepseek"),
        ("backendPort", 8000),
        ("backendTarget", "app.main:app"),
        ("storageDir", "storage"),
    ],
)
def test_refuse_unsafe_target_before_api_request(runtime, field, value):
    root, run, started, _, manifest, save = runtime
    manifest[field] = value
    save()
    with pytest.raises(ValueError):
        validate_run(root, run, process_probe=lambda _: started)
    assert not (root / ".tmp/release-smoke").exists()


@pytest.mark.parametrize("state", ["gone", "reused"])
def test_refuse_missing_or_reused_backend_pid(runtime, state):
    root, run, started, *_ = runtime

    def probe(_):
        return None if state == "gone" else started + timedelta(seconds=10)

    with pytest.raises(IsolationError):
        validate_run(root, run, process_probe=probe)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/api/v1/", "https://example.com/"])
def test_refuse_business_or_external_api_url(runtime, url):
    root, run, started, credentials, _, save = runtime
    credentials["apiBaseUrl"] = url
    save()
    with pytest.raises(ValueError):
        validate_run(root, run, process_probe=lambda _: started)


def test_correct_live_owned_mock_run_allowed(runtime):
    root, run, started, *_ = runtime
    _, manifest = validate_run(root, run, process_probe=lambda _: started)
    assert manifest["databaseName"] == "cp_e2e_release-test"


@pytest.mark.skipif(os.name != 'nt', reason='Windows directory junction guard')
def test_junction_smoke_state_refused_before_password_write(tmp_path):
    import _winapi

    root = tmp_path / 'backend'
    outside = tmp_path / 'outside'
    (root / '.tmp').mkdir(parents=True)
    outside.mkdir()
    link = root / '.tmp/release-smoke'
    _winapi.CreateJunction(str(outside), str(link))
    try:
        with pytest.raises((IsolationError, ValueError), match='Linked'):
            smoke_account(root, 'junction-probe')
        assert list(outside.iterdir()) == []
    finally:
        link.rmdir()  # Remove only the test-created junction, never its target.


@pytest.mark.skipif(os.name != 'nt', reason='Windows directory junction guard')
def test_junction_runtime_refused_before_read_or_process_probe(runtime):
    import _winapi

    root, run, _, _, _, _ = runtime
    original = root / '.tmp/e2e'
    outside = root / 'fixture-state'
    original.rename(outside)
    _winapi.CreateJunction(str(outside), str(original))
    try:
        with pytest.raises((IsolationError, ValueError), match='Linked'):
            validate_run(root, run, process_probe=lambda _: pytest.fail('Probe preceded guard'))
    finally:
        original.rmdir()


@pytest.mark.parametrize("run", ["../careerproof", "release_test", "", "a" * 33])
def test_invalid_run_refused_before_reading_state(tmp_path, run):
    with pytest.raises(ValueError, match="Invalid E2E"):
        validate_run(tmp_path, run)


def test_prepare_uses_child_env_and_existing_launcher(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        settings, "database_url", "postgresql+asyncpg://qa:test@127.0.0.1:5432/careerproof"
    )
    monkeypatch.setenv("E2E_DATABASE_URL", "original-parent-value")
    monkeypatch.setattr(
        "evals.release_smoke.subprocess.run", lambda cmd, **kw: calls.append((cmd, kw))
    )
    prepare_run(tmp_path, "release-test", ".venv", "")
    import os

    assert os.environ["E2E_DATABASE_URL"] == "original-parent-value"
    cmd, kwargs = calls[0]
    assert "Start-E2E.ps1" in cmd[5]
    assert "-SyntheticVerification" in cmd and "-ActivateSyntheticBudget" in cmd
    assert kwargs["env"]["E2E_DATABASE_URL"].endswith("/cp_e2e_release-test")
    assert kwargs["check"] is True


@pytest.mark.parametrize(
    "run,venv,stage,url",
    [
        ("../escape", ".venv", "", "postgresql+asyncpg://qa:test@localhost:5432/careerproof"),
        ("release-test", "../venv", "", "postgresql+asyncpg://qa:test@localhost:5432/careerproof"),
        (
            "release-test",
            ".venv",
            "bad;command",
            "postgresql+asyncpg://qa:test@localhost:5432/careerproof",
        ),
        ("release-test", ".venv", "", "postgresql+asyncpg://qa:test@example.com:5432/careerproof"),
    ],
)
def test_prepare_refuses_unsafe_launch_before_subprocess(
    tmp_path, monkeypatch, run, venv, stage, url
):
    calls = []
    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.setattr("evals.release_smoke.subprocess.run", lambda *a, **kw: calls.append(a))
    with pytest.raises(ValueError):
        prepare_run(tmp_path, run, venv, stage)
    assert not calls


def test_smoke_account_is_separate_and_existing_credentials_never_overwritten(tmp_path):
    account = smoke_account(tmp_path, "release-test")
    assert account["role"] == "student"
    assert account["email"] == "smoke-release-test@example.com"
    assert len(account["password"]) >= 24
    path = tmp_path / ".tmp/release-smoke/release-test.credentials.json"
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        smoke_account(tmp_path, "release-test")
    assert path.read_bytes() == before


def test_smoke_account_invalid_run_cannot_write_private_file(tmp_path):
    with pytest.raises(ValueError):
        smoke_account(tmp_path, "../escape")
    assert not (tmp_path / ".tmp").exists()
