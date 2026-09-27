import base64
import hashlib
import io
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image, PngImagePlugin
from sqlalchemy import select

from app.agents.vision_provider import (
    VISION_PROMPT_VERSION,
    DeepSeekVisionProvider,
    get_vision_provider,
)
from app.core.config import settings
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.enums import TaskStatus
from app.models.identity import StudentProfile
from app.models.portfolio import Project, ProjectVersion
from app.schemas.visual import VisualResponse
from app.services.matching_materials import MatchMaterials, analyze_materials
from app.services.visual_evidence import safe_png, validate_observations, visual_attachments
from app.tests.test_jobs_api import register
from app.tests.test_real_matching import matching_db  # noqa: F401
from app.tools.matcher import RequirementInput


def png():
    out = io.BytesIO()
    meta = PngImagePlugin.PngInfo()
    meta.add_text("private-metadata", "must-strip-this")
    Image.new("RGB", (100, 80), "white").save(out, format="PNG", pnginfo=meta)
    return out.getvalue()


def visual_answer():
    return {
        "image_kind": "monitoring",
        "observations": [
            {
                "description": "图中可见服务状态面板。",
                "visible_text": "status: ok",
                "region": [0.1, 0.1, 0.9, 0.8],
                "needs_verification": "需要源码和运行记录核验真实服务状态。",
            }
        ],
    }


@pytest.mark.parametrize(
    "region", [[0, 0, 2, 1], [0.5, 0, 0.2, 1], [0, 0, 1, float("nan")], [0, 0, 0, 0]]
)
def test_visual_region_rejects_invalid_rectangles(region):
    raw = visual_answer()
    raw["observations"][0]["region"] = region
    with pytest.raises(ValueError):
        VisualResponse.model_validate(raw)


def test_visual_observation_rejects_grades_and_overclaims():
    raw = visual_answer()
    raw["level"] = 3
    with pytest.raises(ValueError):
        validate_observations(raw)
    raw.pop("level")
    raw["observations"][0]["description"] = "证明具备部署能力"
    with pytest.raises(ValueError):
        validate_observations(raw)


async def test_vision_provider_only_sends_one_data_image_and_bounds_request():
    def handler(request):
        body = json.loads(request.content)
        assert body["max_tokens"] == 1000
        assert body["thinking"] == {"type": "disabled"}
        assert body["model"] == "deepseek-flash"
        assert body["response_format"] == {"type": "json_object"}
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        content = body["messages"][1]["content"]
        assert len(content) == 2 and "tools" not in body
        assert base64.b64decode(content[0]["image_url"]["url"].split(",")[1]) == png()
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(visual_answer())}}],
                "usage": {"prompt_tokens": 300, "completion_tokens": 100},
            },
        )

    provider = DeepSeekVisionProvider(
        api_key="synthetic-key",
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )
    assert (await provider.observe(png()))["image_kind"] == "monitoring"
    assert provider.combined_usage().input_tokens == 300
    with pytest.raises(ValueError):
        DeepSeekVisionProvider(
            api_key="synthetic",
            model="deepseek-pro",
            base_url="https://api.deepseek.com",
            timeout_seconds=2,
        )


@pytest.mark.parametrize("failure", [False, True])
async def test_visual_owner_consent_fallback_review_and_reuse(matching_db, monkeypatch, failure):  # noqa: F811
    app, factory = matching_db
    calls = []

    class Provider:
        model = "synthetic-vision"

        async def observe(self, _bytes):
            calls.append(1)
            if failure:
                raise ValueError("Synthetic malformed output")
            return visual_answer()

        def combined_usage(self):
            return None

    monkeypatch.setattr("app.services.visual_evidence.get_vision_provider", lambda: Provider())
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as stranger,
    ):
        user = await register(owner, "visual-owner@example.com", "student")
        await register(stranger, "visual-stranger@example.com", "student")
        async with factory() as session:
            profile = await session.scalar(
                select(StudentProfile).where(StudentProfile.user_id == UUID(user["id"]))
            )
            project = Project(student_id=profile.id, name="合成图片")
            session.add(project)
            await session.flush()
            raw = png()
            settings.storage_base_dir.mkdir(parents=True, exist_ok=True)
            (settings.storage_base_dir / "synthetic.png").write_bytes(raw)
            version = ProjectVersion(
                project_id=project.id,
                version_number=1,
                archive_storage_key="synthetic.png",
                original_filename="x.png",
                content_hash=hashlib.sha256(raw).hexdigest(),
                analysis_status="completed",
            )
            session.add(version)
            await session.commit()
            version_id = str(version.id)
            assert b"must-strip-this" not in safe_png(version)
        endpoint = f"/api/v1/project-versions/{version_id}/visual-review"
        assert (await owner.post(endpoint, json={})).status_code == 422
        assert calls == []
        assert (await stranger.get(endpoint)).status_code == 404
        image = f"/api/v1/project-versions/{version_id}/image"
        assert (await stranger.get(image)).status_code == 404
        source = await owner.get(image)
        assert source.status_code == 200 and "no-store" in source.headers["cache-control"]
        response = await owner.post(endpoint, json={"externalImageConsent": True})
        assert response.status_code == 200, response.text
        result = response.json()["data"]
        assert result["status"] == ("unavailable" if failure else "completed")
        assert "level" not in result and len(calls) == 1
        assert (await owner.get(endpoint)).json()["data"] == result
        if not failure:
            # More than 100 newer observations on unrelated versions must not hide
            # the saved result, trigger a paid repeat, or drop report attachments.
            async with factory() as session:
                session.add_all(
                    [
                        AnalysisTask(
                            created_by=UUID(user["id"]),
                            task_type="visual_review",
                            status=TaskStatus.COMPLETED,
                            input_snapshot={"projectVersionId": str(uuid4())},
                        )
                        for _ in range(101)
                    ]
                )
                await session.commit()
            assert (await owner.get(endpoint)).json()["data"] == result
            assert (await owner.post(endpoint, json={"externalImageConsent": True})).json()["data"][
                "id"
            ] == result["id"]
            assert len(calls) == 1
            review_url = f"/api/v1/visual-reviews/{result['id']}"
            denied = await stranger.patch(review_url, json={"status": "accepted"})
            assert denied.status_code == 404
            reviewed = (
                await owner.patch(review_url, json={"status": "rejected", "note": "区域需要修正"})
            ).json()["data"]
            assert reviewed["reviewStatus"] == "rejected"
            async with factory() as session:
                from app.models.identity import User

                record_user = await session.get(User, UUID(user["id"]))
                attached = await visual_attachments(session, [version_id], record_user)
                assert attached[0]["reviewStatus"] == "rejected"
                assert await visual_attachments(session, [], record_user) == []
                assert list(await session.scalars(select(AiUsageLog))) == []


def test_image_hash_mismatch_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_base_dir", tmp_path)
    (tmp_path / "x.png").write_bytes(png())
    with pytest.raises(Exception, match="图片与保存版本不一致"):
        safe_png(SimpleNamespace(archive_storage_key="x.png", content_hash="wrong"))


def test_ocr_screenshot_sql_is_not_rated_as_source_code(tmp_path):
    text = "[OCR识别文本] SELECT id FROM students; status: ok"
    (tmp_path / "document.txt").write_text(text, encoding="utf-8")
    content = text.encode()
    files = [
        {
            "versionId": "synthetic-image",
            "sourceModality": "image",
            "path": "synthetic-image/document.txt",
            "storageKey": "document.txt",
            "hash": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
    ]
    result = analyze_materials(
        [RequirementInput(uuid4(), "实现SQL查询", "SQL", 5)],
        MatchMaterials("了解SQL", files, []),
        tmp_path,
        enable_semantic=False,
    )
    assert result.items[0].evidence is None and result.items[0].evidence_list == []
    assert any(
        s["status"] == "visual_excluded_from_rating"
        for s in result.retrieval_steps
        if "status" in s
    )


def test_vision_reuses_deepseek_key_and_disables_legacy_selection(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", SecretStr("synthetic-deepseek-key"))
    monkeypatch.setattr(settings, "zhipu_api_key", None)
    selected = get_vision_provider()
    assert selected.name == "deepseek" and selected.model == settings.deepseek_model
    assert selected._max_attempts == 1
    # Inline Base64 is transport data, and user caption text is included in the guard.
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 20000}},
                {"type": "text", "text": "bounded caption"},
            ],
        }
    ]
    assert 1024 < selected._estimate_input_tokens(messages) < 2000
    monkeypatch.setattr(settings, "ai_provider", "zhipu")
    with pytest.raises(ValueError):
        get_vision_provider()
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    with pytest.raises(ValueError):
        get_vision_provider()


async def image_version(factory, user_id, filename="cache-boundary.png"):
    """Owned synthetic image with a real immutable-version hash."""
    async with factory() as session:
        profile = await session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        project = Project(student_id=profile.id, name="视觉缓存边界合成图片")
        session.add(project)
        await session.flush()
        raw = png()
        settings.storage_base_dir.mkdir(parents=True, exist_ok=True)
        (settings.storage_base_dir / filename).write_bytes(raw)
        version = ProjectVersion(
            project_id=project.id,
            version_number=1,
            archive_storage_key=filename,
            original_filename=filename,
            content_hash=hashlib.sha256(raw).hexdigest(),
            analysis_status="completed",
        )
        session.add(version)
        await session.commit()
        return version


def saved_visual(owner_id, version, *, status=TaskStatus.COMPLETED, age=0, **overrides):
    from datetime import UTC, datetime, timedelta

    snapshot = {
        "projectVersionId": str(version.id),
        "sourceHash": version.content_hash,
        "promptVersion": VISION_PROMPT_VERSION,
        "model": "synthetic-vision",
        "observations": visual_answer() if status == TaskStatus.COMPLETED else None,
        "externalImageConsent": True,
        "reviewStatus": "pending",
    }
    snapshot.update(overrides)
    return AnalysisTask(
        created_by=owner_id,
        task_type="visual_review",
        status=status,
        created_at=datetime.now(UTC) - timedelta(seconds=age),
        input_snapshot=snapshot,
    )


@pytest.mark.parametrize("missing", [False, True])
async def test_visual_cache_rechecks_source_before_returning(matching_db, monkeypatch, missing):  # noqa: F811
    app, factory = matching_db

    def forbidden_provider():
        raise AssertionError("Cache source checks must not make any model request")

    monkeypatch.setattr("app.services.visual_evidence.get_vision_provider", forbidden_provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "cache-source@example.com", "student")
        version = await image_version(factory, UUID(user["id"]))
        async with factory() as session:
            session.add(saved_visual(UUID(user["id"]), version))
            await session.commit()
        if missing:
            (settings.storage_base_dir / version.archive_storage_key).unlink()
        else:
            (settings.storage_base_dir / version.archive_storage_key).write_bytes(
                b"changed synthetic source"
            )
        response = await client.post(
            f"/api/v1/project-versions/{version.id}/visual-review",
            json={"externalImageConsent": True},
        )
        assert response.status_code == 409, response.text
        async with factory() as session:
            assert len(list(await session.scalars(select(AnalysisTask)))) == 1
            assert list(await session.scalars(select(AiUsageLog))) == []


@pytest.mark.parametrize(
    "latest_status", [TaskStatus.FAILED, TaskStatus.PENDING, TaskStatus.RUNNING]
)
async def test_new_report_does_not_resurrect_observation_before_latest_failure_or_pending(
    matching_db,  # noqa: F811
    latest_status,
):
    from app.models.identity import User

    app, factory = matching_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "latest-visual@example.com", "student")
        version = await image_version(factory, UUID(user["id"]))
        async with factory() as session:
            session.add_all(
                [
                    saved_visual(UUID(user["id"]), version, age=30),
                    saved_visual(UUID(user["id"]), version, status=latest_status),
                ]
            )
            await session.commit()
            actor = await session.get(User, UUID(user["id"]))
            assert await visual_attachments(session, [version.id], actor) == []
        response = await client.get(f"/api/v1/project-versions/{version.id}/visual-review")
        assert response.json()["data"]["status"] == "unavailable"


@pytest.mark.parametrize(
    "overrides", [{"sourceHash": "wrong-source"}, {"promptVersion": "obsolete-visual-prompt"}]
)
async def test_new_report_omits_stale_hash_or_prompt_observation(matching_db, overrides):  # noqa: F811
    from app.models.identity import User

    app, factory = matching_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "stale-visual@example.com", "student")
        version = await image_version(factory, UUID(user["id"]))
        async with factory() as session:
            session.add_all(
                [
                    saved_visual(UUID(user["id"]), version, age=30),
                    saved_visual(UUID(user["id"]), version, **overrides),
                ]
            )
            await session.commit()
            actor = await session.get(User, UUID(user["id"]))
            assert await visual_attachments(session, [version.id], actor) == []


async def test_visual_attachment_service_enforces_image_ownership_even_with_forged_task_reference(
    matching_db,  # noqa: F811
):
    from app.models.identity import User

    app, factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger,
    ):
        first = await register(owner, "attachment-owner@example.com", "student")
        second = await register(stranger, "attachment-other@example.com", "student")
        version = await image_version(factory, UUID(first["id"]))
        async with factory() as session:
            # Corrupted/imported task metadata must not bypass the source ownership join.
            session.add(saved_visual(UUID(second["id"]), version))
            await session.commit()
            actor = await session.get(User, UUID(second["id"]))
            assert await visual_attachments(session, [version.id], actor) == []


async def test_existing_visual_cache_still_requires_image_consent(matching_db, monkeypatch):  # noqa: F811
    app, factory = matching_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "cached-consent@example.com", "student")
        version = await image_version(factory, UUID(user["id"]))
        async with factory() as session:
            session.add(saved_visual(UUID(user["id"]), version))
            await session.commit()
        response = await client.post(
            f"/api/v1/project-versions/{version.id}/visual-review", json={}
        )
        assert response.status_code == 422


async def test_visual_cache_is_rechecked_after_account_budget_lock(monkeypatch):
    from unittest.mock import AsyncMock

    from app.services.visual_evidence import observe_image

    row = SimpleNamespace(content_hash="frozen-source")
    cached = SimpleNamespace(
        status="completed",
        source_hash=row.content_hash,
        prompt_version=VISION_PROMPT_VERSION,
        observations=visual_answer(),
    )
    latest = AsyncMock(side_effect=[None, cached])
    budget = AsyncMock(return_value=(False, "daily_report_limit", {}))
    monkeypatch.setattr("app.services.visual_evidence.owned_image", AsyncMock(return_value=row))
    monkeypatch.setattr("app.services.visual_evidence.latest_visual", latest)
    monkeypatch.setattr("app.services.visual_evidence.safe_png", lambda _row: png())
    monkeypatch.setattr("app.services.visual_evidence._daily_ai_budget", budget)

    def forbidden_provider():
        raise AssertionError("An observation completed while waiting must not be paid for again")

    monkeypatch.setattr("app.services.visual_evidence.get_vision_provider", forbidden_provider)
    result = await observe_image(
        object(), uuid4(), SimpleNamespace(external_image_consent=True), SimpleNamespace(id=uuid4())
    )
    assert result is cached and latest.await_count == 2 and budget.await_count == 1


@pytest.mark.parametrize("missing", [False, True])
async def test_new_report_omits_missing_or_changed_image_source(matching_db, missing):  # noqa: F811
    from app.models.identity import User

    app, factory = matching_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "attachment-source@example.com", "student")
        version = await image_version(factory, UUID(user["id"]))
        async with factory() as session:
            session.add(saved_visual(UUID(user["id"]), version))
            await session.commit()
            if missing:
                (settings.storage_base_dir / version.archive_storage_key).unlink()
            else:
                (settings.storage_base_dir / version.archive_storage_key).write_bytes(b"changed")
            actor = await session.get(User, UUID(user["id"]))
            assert await visual_attachments(session, [version.id], actor) == []


async def test_new_image_version_does_not_inherit_previous_version_observation(matching_db):  # noqa: F811
    from app.models.identity import User

    app, factory = matching_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "visual-version@example.com", "student")
        version = await image_version(factory, UUID(user["id"]))
        async with factory() as session:
            session.add(saved_visual(UUID(user["id"]), version))
            raw = io.BytesIO()
            Image.new("RGB", (100, 80), "black").save(raw, format="PNG")
            filename = "cache-version-two.png"
            (settings.storage_base_dir / filename).write_bytes(raw.getvalue())
            newer = ProjectVersion(
                project_id=version.project_id,
                version_number=2,
                archive_storage_key=filename,
                original_filename=filename,
                content_hash=hashlib.sha256(raw.getvalue()).hexdigest(),
                analysis_status="completed",
            )
            session.add(newer)
            await session.commit()
            actor = await session.get(User, UUID(user["id"]))
            assert await visual_attachments(session, [newer.id], actor) == []
            older = await visual_attachments(session, [version.id], actor)
            assert len(older) == 1 and older[0]["sourceHash"] == version.content_hash


@pytest.mark.parametrize("field", ["description", "visible_text", "needs_verification"])
def test_visual_output_filters_credentials_in_all_model_text_fields(field):
    raw = visual_answer()
    raw["observations"][0][field] = '面板文字 PASSWORD="synthetic visual private tail"'
    safe = validate_observations(raw).model_dump()
    assert "synthetic visual private tail" not in json.dumps(safe)
    assert "redacted credential" in safe["observations"][0][field]
    assert "synthetic visual private tail" in raw["observations"][0][field]


def test_visual_verification_field_cannot_assert_ability_but_transcription_is_untrusted():
    raw = visual_answer()
    raw["observations"][0]["needs_verification"] = "证明具备部署能力"
    with pytest.raises(ValueError):
        validate_observations(raw)
    raw["observations"][0]["needs_verification"] = "不能证明具备部署能力，需核对源码。"
    raw["observations"][0]["visible_text"] = "测试全部通过"
    assert validate_observations(raw).observations[0].visible_text == "测试全部通过"


@pytest.mark.parametrize("invalid", [False, True])
async def test_saved_visual_read_checks_legacy_output_without_modifying_snapshot(
    matching_db,  # noqa: F811
    monkeypatch,
    invalid,
):
    from app.models.identity import User

    app, factory = matching_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "legacy-visual-output@example.com", "student")
        version = await image_version(factory, UUID(user["id"]))
        old = visual_answer()
        old["observations"][0]["visible_text"] = 'PASSWORD="synthetic cached private tail"'
        if invalid:
            old["observations"][0]["needs_verification"] = "证明具备部署能力"
        async with factory() as session:
            task = saved_visual(UUID(user["id"]), version, observations=old)
            session.add(task)
            await session.commit()
            task_id = task.id
        endpoint = f"/api/v1/project-versions/{version.id}/visual-review"
        response = await client.get(endpoint)
        assert response.status_code == 200, response.text
        result = response.json()["data"]
        assert "synthetic cached private tail" not in response.text
        assert result["status"] == ("unavailable" if invalid else "completed")
        if invalid:
            assert (
                result["failureKind"] == "saved_invalid_output" and result["observations"] is None
            )
            review = await client.patch(
                f"/api/v1/visual-reviews/{task_id}", json={"status": "accepted"}
            )
            assert review.status_code == 409
        async with factory() as session:
            saved = await session.get(AnalysisTask, task_id)
            assert saved.input_snapshot["observations"] == old
            actor = await session.get(User, UUID(user["id"]))
            attachments = await visual_attachments(session, [version.id], actor)
            assert len(attachments) == (0 if invalid else 1)
            assert "synthetic cached private tail" not in json.dumps(attachments)

        calls = []

        class Provider:
            model = "synthetic-vision"

            async def observe(self, _bytes):
                calls.append(1)
                return visual_answer()

            def combined_usage(self):
                return None

        monkeypatch.setattr("app.services.visual_evidence.get_vision_provider", lambda: Provider())
        regenerated = await client.post(endpoint, json={"externalImageConsent": True})
        assert regenerated.status_code == 200, regenerated.text
        assert regenerated.json()["data"]["status"] == "completed"
        assert len(calls) == (1 if invalid else 0)
        assert "synthetic cached private tail" not in regenerated.text


@pytest.mark.parametrize("invalid", [False, True])
async def test_visual_paid_usage_kept_when_output_is_filtered_or_rejected(
    matching_db,  # noqa: F811
    monkeypatch,
    invalid,
):
    from app.agents.contracts import ModelUsage
    from app.models.identity import User

    app, factory = matching_db
    raw = visual_answer()
    raw["observations"][0]["visible_text"] = 'PASSWORD="synthetic returned private tail"'
    if invalid:
        raw["observations"][0]["needs_verification"] = "证明具备部署能力"

    class Provider:
        name = "synthetic"
        model = "synthetic-vision"

        async def observe(self, _bytes):
            return raw

        def combined_usage(self):
            return ModelUsage(input_tokens=17, output_tokens=13, latency_ms=5)

    monkeypatch.setattr("app.services.visual_evidence.get_vision_provider", lambda: Provider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "validated-visual-output@example.com", "student")
        version = await image_version(factory, UUID(user["id"]))
        response = await client.post(
            f"/api/v1/project-versions/{version.id}/visual-review",
            json={"externalImageConsent": True},
        )
        assert response.status_code == 200, response.text
        result = response.json()["data"]
        assert result["status"] == ("unavailable" if invalid else "completed")
        assert "synthetic returned private tail" not in response.text
        async with factory() as session:
            task = await session.get(AnalysisTask, UUID(result["id"]))
            assert "synthetic returned private tail" not in json.dumps(task.input_snapshot)
            usage = list(await session.scalars(select(AiUsageLog)))
            assert len(usage) == 1
            assert usage[0].input_tokens == 17 and usage[0].output_tokens == 13
            actor = await session.get(User, UUID(user["id"]))
            attached = await visual_attachments(session, [version.id], actor)
            assert len(attached) == (0 if invalid else 1)
            assert (settings.storage_base_dir / version.archive_storage_key).read_bytes() == png()


@pytest.mark.parametrize(
    "condition", ["new_failure", "source_changed", "prompt_changed", "old_failure"]
)
async def test_waiting_visual_request_shares_only_a_new_matching_failure(monkeypatch, condition):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.agents.vision_provider import VISION_PROMPT_VERSION
    from app.core.exceptions import AppError
    from app.services.visual_evidence import observe_image

    row = SimpleNamespace(content_hash="current-hash")
    unavailable = SimpleNamespace(
        id="new-attempt",
        status="unavailable",
        observations=None,
        source_hash="other" if condition == "source_changed" else "current-hash",
        prompt_version="old-prompt" if condition == "prompt_changed" else VISION_PROMPT_VERSION,
    )
    before = unavailable if condition == "old_failure" else None
    monkeypatch.setattr("app.services.visual_evidence.owned_image", AsyncMock(return_value=row))
    monkeypatch.setattr("app.services.visual_evidence.safe_png", lambda _row: b"synthetic")
    monkeypatch.setattr(
        "app.services.visual_evidence.latest_visual", AsyncMock(side_effect=[before, unavailable])
    )
    monkeypatch.setattr(
        "app.services.visual_evidence._daily_ai_budget",
        AsyncMock(return_value=(False, "daily_report_limit", {})),
    )

    def forbidden():
        pytest.fail("A waiting request or a budget rejection must not call the model")

    monkeypatch.setattr("app.services.visual_evidence.get_vision_provider", forbidden)
    request = SimpleNamespace(external_image_consent=True)
    user = SimpleNamespace(id="synthetic-owner")
    if condition == "new_failure":
        assert await observe_image(object(), "synthetic-version", request, user) is unavailable
    else:
        with pytest.raises(AppError) as error:
            await observe_image(object(), "synthetic-version", request, user)
        assert error.value.status_code == 429
