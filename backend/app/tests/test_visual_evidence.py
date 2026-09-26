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

from app.agents.vision_provider import ZhipuVisionProvider
from app.core.config import settings
from app.models.analysis import AiUsageLog
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
    return {"image_kind": "monitoring", "observations": [{
        "description": "图中可见服务状态面板。", "visible_text": "status: ok",
        "region": [0.1, 0.1, 0.9, 0.8],
        "needs_verification": "需要源码和运行记录核验真实服务状态。"}]}


@pytest.mark.parametrize("region", [[0, 0, 2, 1], [0.5, 0, 0.2, 1],
                                    [0, 0, 1, float("nan")], [0, 0, 0, 0]])
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
        content = body["messages"][1]["content"]
        assert len(content) == 2 and "tools" not in body
        assert base64.b64decode(content[0]["image_url"]["url"].split(",")[1]) == png()
        return httpx.Response(200, json={"choices": [{"message": {
            "content": json.dumps(visual_answer())}}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 100}})
    provider = ZhipuVisionProvider(api_key="synthetic-key", model="glm-4.6v-flash",
                                  base_url="https://open.bigmodel.cn/api/paas/v4",
                                  timeout_seconds=2, transport=httpx.MockTransport(handler))
    assert (await provider.observe(png()))["image_kind"] == "monitoring"
    assert provider.combined_usage().input_tokens == 300
    with pytest.raises(ValueError):
        ZhipuVisionProvider(api_key="synthetic", model="glm-4.6v",
                            base_url="https://open.bigmodel.cn/api/paas/v4", timeout_seconds=2)


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
    async with (AsyncClient(transport=transport, base_url="http://test") as owner,
                AsyncClient(transport=transport, base_url="http://test") as stranger):
        user = await register(owner, "visual-owner@example.com", "student")
        await register(stranger, "visual-stranger@example.com", "student")
        async with factory() as session:
            profile = await session.scalar(select(StudentProfile).where(
                StudentProfile.user_id == UUID(user["id"])))
            project = Project(student_id=profile.id, name="合成图片")
            session.add(project)
            await session.flush()
            raw = png()
            settings.storage_base_dir.mkdir(parents=True, exist_ok=True)
            (settings.storage_base_dir / "synthetic.png").write_bytes(raw)
            version = ProjectVersion(project_id=project.id, version_number=1,
                                     archive_storage_key="synthetic.png", original_filename="x.png",
                                     content_hash=hashlib.sha256(raw).hexdigest(),
                                     analysis_status="completed")
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
            assert (await owner.post(endpoint, json={"externalImageConsent": True})).json()[
                "data"]["id"] == result["id"]
            assert len(calls) == 1
            review_url = f"/api/v1/visual-reviews/{result['id']}"
            denied = await stranger.patch(review_url, json={"status": "accepted"})
            assert denied.status_code == 404
            reviewed = (await owner.patch(review_url, json={"status": "rejected",
                                                            "note": "区域需要修正"})).json()["data"]
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
    files = [{"versionId": "synthetic-image", "sourceModality": "image",
              "path": "synthetic-image/document.txt", "storageKey": "document.txt",
              "hash": hashlib.sha256(content).hexdigest(), "size": len(content)}]
    result = analyze_materials([RequirementInput(uuid4(), "实现SQL查询", "SQL", 5)],
                               MatchMaterials("了解SQL", files, []), tmp_path,
                               enable_semantic=False)
    assert result.items[0].evidence is None and result.items[0].evidence_list == []
    assert any(s["status"] == "visual_excluded_from_rating" for s in result.retrieval_steps
               if "status" in s)
