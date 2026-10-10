from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.services.application_verification import validate_verification
from evals.e2e_verification import SyntheticVerificationProvider, create_app, validate_environment

RUN = "upgrade-20261010"
DATABASE = f"postgresql+asyncpg://synthetic:synthetic@127.0.0.1:5432/cp_e2e_{RUN}"
STORAGE = Path(__file__).resolve().parents[1] / ".tmp" / "e2e-storage" / RUN


@pytest.mark.parametrize("change", [
    {"run": "../business"}, {"database_url": DATABASE.replace("cp_e2e_" + RUN, "careerproof")},
    {"database_url": DATABASE.replace("127.0.0.1", "vendor.example")},
    {"database_url": DATABASE + "?options=business"},
    {"storage": STORAGE.parent}, {"external_enabled": True}, {"provider": "deepseek"},
])
def test_refuses_non_isolated_environments(change):
    arguments = dict(run=RUN, database_url=DATABASE, storage=STORAGE,
                     external_enabled=False, provider="mock")
    with pytest.raises(ValueError):
        validate_environment(**(arguments | change))


def test_accepts_only_run_bound_environment():
    validate_environment(RUN, DATABASE, STORAGE, False, "mock")


def test_factory_refuses_business_database_before_overriding_product(monkeypatch):
    from app.core.config import settings
    from app.services import application_verification as verification

    original_identity = verification._identity
    original_provider = verification.get_ai_provider
    monkeypatch.setenv("E2E_SYNTHETIC_VERIFICATION_RUN", RUN)
    monkeypatch.setattr(settings, "database_url", DATABASE.replace("cp_e2e_" + RUN, "careerproof"))
    with pytest.raises(ValueError):
        create_app()
    assert verification._identity is original_identity
    assert verification.get_ai_provider is original_provider


def test_factory_overrides_only_verification_not_main_matching(monkeypatch):
    from app.agents import provider as matching
    from app.core.config import settings
    from app.services import application_verification as verification

    original_matching = matching.get_ai_provider
    monkeypatch.setenv("E2E_SYNTHETIC_VERIFICATION_RUN", RUN)
    monkeypatch.setattr(settings, "database_url", DATABASE)
    monkeypatch.setattr(settings, "storage_base_dir", STORAGE)
    monkeypatch.setattr(settings, "ai_external_enabled", False)
    monkeypatch.setattr(settings, "ai_provider", "mock")
    # Register originals for restoration after the factory's process-local overrides.
    monkeypatch.setattr(verification, "_identity", verification._identity)
    monkeypatch.setattr(verification, "get_ai_provider", verification.get_ai_provider)
    app = create_app()
    assert app is not None
    assert verification._identity() == ("e2e-mock", "deepseek-flash")
    assert verification.get_ai_provider().name == "e2e-mock"
    assert matching.get_ai_provider is original_matching
    assert matching.get_ai_provider().name == "mock"


@pytest.mark.asyncio
async def test_budget_activation_refuses_business_database_before_connection(monkeypatch):
    from app.core.config import settings
    from evals import activate_e2e_budget

    def forbidden_connection(*args, **kwargs):
        raise AssertionError("Invalid environment reached database connection")

    monkeypatch.setattr(settings, "database_url", DATABASE.replace("cp_e2e_" + RUN, "careerproof"))
    monkeypatch.setattr(activate_e2e_budget, "create_async_engine", forbidden_connection)
    with pytest.raises(ValueError):
        await activate_e2e_budget.activate(RUN)


@pytest.mark.asyncio
async def test_actual_provider_uses_only_mock_transport_and_validates_output(monkeypatch):
    async def forbidden_network(*args, **kwargs):
        raise AssertionError("Synthetic verification attempted real network transport")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden_network)
    provider = SyntheticVerificationProvider()
    requirement = str(uuid4())
    raw = await provider.generate_bounded_json(
        system="Synthetic verification only",
        data={"fixedReportRequirements": [{"requirementId": requirement}]},
        max_tokens=3000,
    )
    result = validate_verification(raw, {"items": [{"requirementId": requirement}]})
    assert len(result.items) == 1
    assert result.items[0].visible_support is None
    assert result.items[0].citation_ids == []
    assert provider.name == "e2e-mock"
    assert isinstance(provider._transport, httpx.MockTransport)
