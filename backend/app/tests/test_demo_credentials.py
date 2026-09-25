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
