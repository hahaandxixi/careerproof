"""First-batch dependency upgrade regressions (multipart/Pillow/PyJWT).

Task card 20261009-DEP-01: exercise the real failure paths at the real
entry points instead of comparing version numbers — malformed multipart
boundaries and upload filename traversal, Pillow decode/pixel limits in
safe_png / vision preflight / OCR preflight, and PyJWT malformed-token
rejection plus legacy-token compatibility. The upgraded libraries
themselves are never mocked.
"""

from __future__ import annotations

import hashlib
import io
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from app.agents.vision_provider import DeepSeekVisionProvider
from app.core import security
from app.core.config import settings
from app.core.exceptions import AppError
from app.services.visual_evidence import safe_png
from app.tests.test_portfolio_api import (  # noqa: F401
    app_database,  # noqa: F401
    project_zip,
    student,
)
from app.tools import ocr

# --- python-multipart: parser-level failure paths --------------------------


async def test_multipart_boundary_mismatch_is_rejected_cleanly(student):  # noqa: F811
    """Body separator differs from the boundary declared in the header."""
    project = (
        await student.post("/api/v1/projects", json={"name": "dep23", "requestId": str(uuid4())})
    ).json()["data"]
    path = f"/api/v1/projects/{project['id']}/versions"
    body = b"--realseparator\r\n"  # header will declare a different boundary
    response = await student.post(
        path,
        content=body,
        headers={"content-type": "multipart/form-data; boundary=declared"},
    )
    assert response.status_code in (400, 422), response.text


async def test_multipart_truncated_body_is_rejected_cleanly(student):  # noqa: F811
    """Cut-off body must not crash the parser or the upload endpoint."""
    project = (
        await student.post("/api/v1/projects", json={"name": "dep23b", "requestId": str(uuid4())})
    ).json()["data"]
    path = f"/api/v1/projects/{project['id']}/versions"
    declared = "dep23cut"
    body = (
        f"--{declared}\r\n"
        f'Content-Disposition: form-data; name="requestId"\r\n\r\n{uuid4()}\r\n'
        f"--{declared}\r\n"
        'Content-Disposition: form-data; name="file"; filename="source.zip"\r\n'
        "Content-Type: application/zip\r\n\r\nPK"  # no closing separator
    ).encode()
    response = await student.post(
        path, content=body, headers={"content-type": f"multipart/form-data; boundary={declared}"}
    )
    assert response.status_code in (400, 422), response.text


async def test_multipart_filename_traversal_is_neutralized(student, tmp_path, monkeypatch):  # noqa: F811
    storage_dir = tmp_path / "storage"
    monkeypatch.setattr(settings, "storage_base_dir", storage_dir)
    project = (
        await student.post("/api/v1/projects", json={"name": "dep23t", "requestId": str(uuid4())})
    ).json()["data"]
    path = f"/api/v1/projects/{project['id']}/versions"
    key = str(uuid4())
    response = await student.post(
        path,
        data={"requestId": key, "materialRole": "reference"},
        files={"file": ("../../evil.zip", project_zip(), "application/zip")},
    )
    assert response.status_code == 202, response.text
    versions = (await student.get(path)).json()["data"]
    assert len(versions) == 1
    stored = [p for p in storage_dir.rglob("*") if p.is_file()]
    assert stored, "upload must persist inside the storage base dir"
    for entry in stored:
        assert ".." not in entry.parts
        assert storage_dir.resolve() in entry.resolve().parents


# --- Pillow: decode and pixel limits at the real entry points --------------


def _stored_image(tmp_path, monkeypatch, data: bytes):
    monkeypatch.setattr(settings, "storage_base_dir", tmp_path / "storage")
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "dep23.png").write_bytes(data)
    return SimpleNamespace(
        archive_storage_key="dep23.png", content_hash=hashlib.sha256(data).hexdigest()
    )


def _png_bytes(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_safe_png_rejects_corrupt_bytes(tmp_path, monkeypatch):
    row = _stored_image(tmp_path, monkeypatch, b"definitely-not-an-image")
    with pytest.raises(AppError) as exc:
        safe_png(row)
    assert exc.value.code == 4024


def test_safe_png_rejects_pixels_above_app_limit(tmp_path, monkeypatch):
    # 6000*4000 = 24M pixels > settings.ocr_max_image_pixels (20M default)
    row = _stored_image(tmp_path, monkeypatch, _png_bytes((6000, 4000)))
    with pytest.raises(AppError) as exc:
        safe_png(row)
    assert exc.value.code == 4026


def _vision_provider() -> DeepSeekVisionProvider:
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return DeepSeekVisionProvider(
        api_key="synthetic-key",
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )


async def test_vision_preflight_rejects_oversize_bytes():
    with pytest.raises(ValueError, match="2MB"):
        await _vision_provider().observe(b"x" * (2 * 1024 * 1024 + 1))


async def test_vision_preflight_rejects_non_png():
    buffer = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(buffer, format="JPEG")
    with pytest.raises(ValueError, match="normalized PNG"):
        await _vision_provider().observe(buffer.getvalue())


async def test_vision_preflight_rejects_oversize_dimensions():
    with pytest.raises(ValueError, match="1280"):
        await _vision_provider().observe(_png_bytes((1281, 8)))


def test_ocr_preflight_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ocr_enabled", False)
    with pytest.raises(AppError) as disabled:
        ocr.recognize_image(b"anything")
    assert disabled.value.code == 4025

    monkeypatch.setattr(settings, "ocr_enabled", True)
    with pytest.raises(AppError) as corrupt:
        ocr.recognize_image(b"corrupt-image-bytes")
    assert corrupt.value.code == 4024

    oversize = _png_bytes((6000, 4000))
    with pytest.raises(AppError) as too_many_pixels:
        ocr.recognize_image(oversize)
    assert too_many_pixels.value.code == 4026


# --- PyJWT: malformed rejection and legacy-token compatibility -------------

# Issued with PyJWT 2.10.1 (baseline venv) using HS256 and a synthetic
# secret; exp=4070880000 (2099-01-01) so the fixture stays deterministic.
LEGACY_PYJWT_2101_REFRESH_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDEiLCJyb2xlIjoic"
    "3R1ZGVudCIsInR5cGUiOiJyZWZyZXNoIiwianRpIjoiZGVwMjMtbGVnYWN5LWNvbXBhdCIsIml"
    "hdCI6MTc2MDAwMDAwMCwiZXhwIjo0MDcwODgwMDAwfQ."
    "Ifs63dP2UK1iXqX3tx0GvjkB3zY5UY3G8ii3qRmw2LQ"
)

MALFORMED_TOKENS = [
    "",
    "not-a-jwt",
    "a.b",
    "a.b.c.d",
    "x.y.z",
    # {"alg":"HS256"} header but the payload is not JSON
    "eyJhbGciOiJIUzI1NiJ9.notjson.sig",
    # payload decodes to a JSON array, not an object
    "eyJhbGciOiJIUzI1NiJ9.W10.sig",
]


@pytest.mark.parametrize("token", MALFORMED_TOKENS)
def test_decode_token_rejects_malformed_tokens(token, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "dep23-regression-secret")
    with pytest.raises(AppError) as exc:
        security.decode_token(token, "refresh")
    assert exc.value.code == 4010


def test_legacy_pytjwt_2101_token_still_decodes(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "dep23-regression-secret")
    payload = security.decode_token(LEGACY_PYJWT_2101_REFRESH_TOKEN, "refresh")
    assert payload["sub"] == "00000000-0000-0000-0000-000000000001"
    assert payload["role"] == "student"
    assert payload["jti"] == "dep23-legacy-compat"
