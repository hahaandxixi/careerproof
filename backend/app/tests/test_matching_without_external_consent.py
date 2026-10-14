"""A local report remains usable without consenting to external model requests."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.agents.provider import DeepSeekProvider
from app.core.config import settings
from app.models.ai_request_attempt import AiRequestAttempt
from app.tests.test_real_matching import (
    create_job,
    match_report,
    register,
    upload_materials,
)
from app.tests.test_real_matching import (
    matching_db as matching_db,
)


@pytest.mark.asyncio
async def test_unconsented_report_has_no_physical_model_requests(
    matching_db, monkeypatch,  # noqa: F811 - imported pytest fixture injection
):
    app, factory = matching_db
    calls = []

    async def refuse_completion(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Unconsented model request attempted")

    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "synthetic-test-key")
    monkeypatch.setattr(DeepSeekProvider, "_completion", refuse_completion)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as hr, AsyncClient(
        transport=transport, base_url="http://test"
    ) as student:
        await register(hr, "consent-owner@example.com")
        job = await create_job(hr)
        await register(student, "consent-student@example.com", "student")
        resume, _, version = await upload_materials(student)
        report = await match_report(
            student, job, resume, version, externalAiConsent=False
        )
        assert report["analysisMode"] == "rules"
        assert report["items"] and any(item["evidenceList"] for item in report["items"])
        assert calls == []
        async with factory() as session:
            from uuid import UUID

            attempts = await session.scalar(select(func.count()).select_from(
                AiRequestAttempt
            ).where(AiRequestAttempt.analysis_task_id == UUID(report["taskId"])))
            assert attempts == 0

