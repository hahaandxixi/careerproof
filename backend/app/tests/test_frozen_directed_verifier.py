import pytest
from pydantic import SecretStr

from app.core.config import settings
from evals import verify_frozen_directed as verifier


@pytest.mark.asyncio
async def test_paid_flag_required_before_material_loading(monkeypatch):
    monkeypatch.setattr(
        verifier, "synthetic_case", lambda: pytest.fail("No materials before paid opt-in")
    )
    with pytest.raises(SystemExit) as error:
        await verifier.main(["--live"])
    assert error.value.code == 2


@pytest.mark.asyncio
async def test_default_does_not_construct_or_call_provider(monkeypatch, capsys):
    monkeypatch.setattr(
        verifier, "run_evidence_workflow", lambda *a, **k: pytest.fail("No API in default")
    )
    assert await verifier.main([]) == 0
    assert '"externalApiCalls": 0' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_existing_record_refused_before_paid_call(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", SecretStr("offline-placeholder"))
    output = tmp_path / "frozen.json"
    output.write_text("original record", encoding="utf-8")
    monkeypatch.setattr(
        verifier, "run_evidence_workflow", lambda *a, **k: pytest.fail("No paid call")
    )
    with pytest.raises(FileExistsError):
        await verifier.main(["--live", "--allow-paid", "--output", str(output)])
    assert output.read_text(encoding="utf-8") == "original record"
