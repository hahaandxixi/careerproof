"""Production startup must reject public secrets and conceal debug surfaces."""

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app

SAFE_TEST_SECRET = "isolated-config-test-secret-not-for-deployment-123"


def test_production_rejects_omitted_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="production")


@pytest.mark.parametrize(
    "secret",
    [
        "development-only-secret-change-before-production",
        "replace-with-at-least-32-random-characters",
        "short-secret",
        " " * 48,
    ],
)
def test_production_rejects_public_or_weak_secrets(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="production", jwt_secret=secret)


@pytest.mark.parametrize("debug", [True, False])
def test_production_always_disables_debug(debug):
    config = Settings(
        _env_file=None, app_env="production", jwt_secret=SAFE_TEST_SECRET, debug=debug
    )
    assert config.debug is False
    assert config.jwt_secret == SAFE_TEST_SECRET


def test_production_environment_variables_are_validated(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("JWT_SECRET", SAFE_TEST_SECRET)
    assert Settings(_env_file=None).debug is False


@pytest.mark.parametrize("environment", ["development", "test"])
def test_local_environments_keep_explicit_debug_and_public_secret(environment):
    config = Settings(_env_file=None, app_env=environment, jwt_secret="local", debug=True)
    assert config.debug is True
    assert config.jwt_secret == "local"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_production_disables_documentation_routes(monkeypatch, path):
    config = Settings(_env_file=None, app_env="production", jwt_secret=SAFE_TEST_SECRET)
    monkeypatch.setattr("app.main.settings", config)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path)).status_code == 404


async def test_production_unhandled_error_does_not_expose_traceback(monkeypatch):
    config = Settings(
        _env_file=None, app_env="production", jwt_secret=SAFE_TEST_SECRET, debug=True
    )
    monkeypatch.setattr("app.main.settings", config)
    app = create_app()

    @app.get("/__isolated_error_test")
    async def fail():
        raise RuntimeError("private-runtime-marker")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/__isolated_error_test")
    assert response.status_code == 500
    assert "private-runtime-marker" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize("environment", ["development", "test"])
async def test_local_documentation_remains_available(monkeypatch, environment):
    config = Settings(_env_file=None, app_env=environment)
    monkeypatch.setattr("app.main.settings", config)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/openapi.json")).status_code == 200
