import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def disable_external_ai_for_tests(monkeypatch):
    """Automated tests never consume a developer's real model quota from .env."""
    monkeypatch.setattr(settings, "ai_external_enabled", False)
    monkeypatch.setattr(settings, "ai_provider", "mock")
