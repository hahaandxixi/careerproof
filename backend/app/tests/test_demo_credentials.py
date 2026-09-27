"""Demo account credentials stay local and must not have a source-code default."""

import json

import pytest

from evals import demo_credentials


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(demo_credentials, "CREDENTIALS_PATH", tmp_path / "demo.json")
    for name in ("DEMO_STUDENT_EMAIL", "DEMO_ENTERPRISE_EMAIL", "DEMO_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


def test_demo_credentials_require_local_configuration():
    with pytest.raises(RuntimeError, match="Local demo credentials missing"):
        demo_credentials.get_demo_credentials("student")


def test_demo_credentials_read_local_file_and_reject_partial_override(monkeypatch):
    demo_credentials.CREDENTIALS_PATH.write_text(json.dumps({
        "studentEmail": "student-test@example.com",
        "enterpriseEmail": "enterprise-test@example.com",
        "password": "synthetic-only-password",
    }), encoding="utf-8")
    assert demo_credentials.get_demo_credentials("student") == {
        "email": "student-test@example.com", "password": "synthetic-only-password"
    }
    monkeypatch.setenv("DEMO_PASSWORD", "another-synthetic-password")
    with pytest.raises(RuntimeError, match="all three"):
        demo_credentials.get_demo_credentials("enterprise")


def test_complete_environment_overrides_local_file(monkeypatch):
    monkeypatch.setenv("DEMO_STUDENT_EMAIL", "other-student@example.com")
    monkeypatch.setenv("DEMO_ENTERPRISE_EMAIL", "other-enterprise@example.com")
    monkeypatch.setenv("DEMO_PASSWORD", "another-synthetic-password")
    assert demo_credentials.get_demo_credentials("enterprise") == {
        "email": "other-enterprise@example.com", "password": "another-synthetic-password"
    }


@pytest.mark.parametrize("changes", [
    {"enterpriseEmail": "invalid@"},
    {"enterpriseEmail": "STUDENT-TEST@example.com"},
    {"password": "x" * 129},
])
def test_student_lookup_rejects_invalid_pair_without_exposing_credentials(changes):
    values = {
        "studentEmail": "student-test@example.com",
        "enterpriseEmail": "enterprise-test@example.com",
        "password": "synthetic-only-password",
        **changes,
    }
    demo_credentials.CREDENTIALS_PATH.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(RuntimeError) as caught:
        demo_credentials.get_demo_credentials("student")
    assert values["password"] not in str(caught.value)
    assert values["enterpriseEmail"] not in str(caught.value)


@pytest.mark.parametrize("values", [[], None, "synthetic-only-password", {"password": 123}])
def test_malformed_local_credentials_fail_with_safe_error(values):
    demo_credentials.CREDENTIALS_PATH.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(RuntimeError):
        demo_credentials.get_demo_credentials("student")


def test_environment_preserves_password_exactly(monkeypatch):
    monkeypatch.setenv("DEMO_STUDENT_EMAIL", "student-test@example.com")
    monkeypatch.setenv("DEMO_ENTERPRISE_EMAIL", "enterprise-test@example.com")
    monkeypatch.setenv("DEMO_PASSWORD", " synthetic-only-password ")
    assert demo_credentials.get_demo_credentials("student")["password"] == (
        " synthetic-only-password "
    )


def test_seed_rejects_invalid_pair_before_network(monkeypatch):
    from evals import seed_demo

    demo_credentials.CREDENTIALS_PATH.write_text(json.dumps({
        "studentEmail": "student-test@example.com",
        "enterpriseEmail": "invalid@",
        "password": "synthetic-only-password",
    }), encoding="utf-8")

    def unexpected_client(*args, **kwargs):
        pytest.fail("Credentials must be validated before creating an HTTP client")

    monkeypatch.setattr(seed_demo.httpx, "Client", unexpected_client)
    with pytest.raises(RuntimeError):
        seed_demo.seed()


def test_seed_password_mismatch_stops_without_reset_or_job_creation(monkeypatch):
    import httpx

    from evals import seed_demo

    original = json.dumps({
        "studentEmail": "student-test@example.com",
        "enterpriseEmail": "enterprise-test@example.com",
        "password": "synthetic-only-password",
    })
    demo_credentials.CREDENTIALS_PATH.write_text(original, encoding="utf-8")
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/register"):
            return httpx.Response(409, json={"message": "Already registered"})
        if request.url.path.endswith("/login"):
            return httpx.Response(401, json={"message": "Invalid credentials"})
        pytest.fail("Password mismatch must not continue to any mutation or retry")

    client_class = httpx.Client
    monkeypatch.setattr(seed_demo.httpx, "Client", lambda **kwargs: client_class(
        **kwargs, transport=httpx.MockTransport(handle)
    ))
    with pytest.raises(RuntimeError, match="does not reset") as caught:
        seed_demo.seed()
    assert "synthetic-only-password" not in str(caught.value)
    assert "student-test@example.com" not in str(caught.value)
    assert calls == [
        ("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/login")
    ]
    assert demo_credentials.CREDENTIALS_PATH.read_text(encoding="utf-8") == original


def test_local_validator_does_not_print_credentials(monkeypatch, capsys):
    import runpy
    from pathlib import Path

    # Execute the real CLI with environment configuration, without reading user files.
    monkeypatch.setenv("DEMO_STUDENT_EMAIL", "student-test@example.com")
    monkeypatch.setenv("DEMO_ENTERPRISE_EMAIL", "enterprise-test@example.com")
    monkeypatch.setenv("DEMO_PASSWORD", "synthetic-only-password")
    runpy.run_path(str(Path(demo_credentials.__file__)), run_name="__main__")
    output = capsys.readouterr().out
    assert "no network request or account change" in output
    assert "synthetic-only-password" not in output
    assert "student-test@example.com" not in output
