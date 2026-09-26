"""Owner-scoped screenshot observations and local review, isolated from grades."""

import asyncio
import hashlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from app.agents.contracts import overclaim_flags
from app.agents.evidence_workflow import _model_semaphore
from app.agents.provider import _redact_external_value
from app.agents.vision_provider import VISION_PROMPT_VERSION, get_vision_provider
from app.core.config import settings
from app.core.exceptions import AppError
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.enums import TaskStatus, UserRole
from app.models.identity import StudentProfile
from app.models.portfolio import Project, ProjectVersion
from app.schemas.visual import VisualResponse, VisualReviewView
from app.services.analysis import _daily_ai_budget
from app.tools.storage import LocalStorage


async def owned_image(session, version_id, user):
    if user.role != UserRole.STUDENT:
        raise AppError("图片材料不存在或无权访问", code=4043, status_code=404)
    row = await session.scalar(select(ProjectVersion).join(Project).join(
        StudentProfile, StudentProfile.id == Project.student_id).where(
        ProjectVersion.id == UUID(str(version_id)), StudentProfile.user_id == user.id))
    if not row:
        raise AppError("图片材料不存在或无权访问", code=4043, status_code=404)
    suffix = Path(row.original_filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        raise AppError("视觉观察仅支持单张图片作品；PDF请先使用本地OCR", code=4227,
                       status_code=422)
    return row


def safe_png(row):
    raw = LocalStorage(settings.storage_base_dir).resolve(row.archive_storage_key).read_bytes()
    if len(raw) > 10 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != row.content_hash:
        raise AppError("图片与保存版本不一致，请重新上传", code=4096, status_code=409)
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.width * image.height > settings.ocr_max_image_pixels:
                raise AppError("图片像素过大，请压缩后重试", code=4026, status_code=413)
            # Re-encode without EXIF/comments. Pixel content is NOT automatically anonymized.
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            normalized.thumbnail((1280, 1280))
            output = BytesIO()
            normalized.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise AppError("图片无法读取", code=4024, status_code=422) from exc


def view(task):
    saved = task.input_snapshot
    created = task.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return VisualReviewView(id=task.id, project_version_id=saved["projectVersionId"],
                            source_hash=saved["sourceHash"],
                            status="completed" if task.status == TaskStatus.COMPLETED
                            else "unavailable", model=saved.get("model"),
                            failure_kind=saved.get("failureKind"),
                            prompt_version=saved["promptVersion"],
                            observations=saved.get("observations"), usage=saved.get("usage"),
                            review_status=saved.get("reviewStatus", "pending"),
                            reviewer_note=saved.get("reviewerNote", ""),
                            reviewed_at=saved.get("reviewedAt"), created_at=created)


async def latest_visual(session, version_id, user):
    await owned_image(session, version_id, user)
    task = await session.scalar(select(AnalysisTask).where(
        AnalysisTask.created_by == user.id, AnalysisTask.task_type == "visual_review",
        AnalysisTask.input_snapshot["projectVersionId"].as_string() == str(version_id)
    ).order_by(AnalysisTask.created_at.desc()).limit(1))
    return view(task) if task else None


def validate_observations(raw):
    parsed = VisualResponse.model_validate(raw)
    for item in parsed.observations:
        # Reject capability/verification assertions; a cautious caveat is not evidence.
        if overclaim_flags(item.description):
            raise ValueError("Vision description overclaims proof")
    return VisualResponse.model_validate(_redact_external_value(parsed.model_dump()))


async def observe_image(session, version_id, request, user):
    row = await owned_image(session, version_id, user)
    if not request.external_image_consent:
        raise AppError("请确认原图已去除敏感信息并允许发送至智谱视觉模型", code=4224,
                       status_code=422)
    saved = await latest_visual(session, version_id, user)
    if (saved and saved.status == "completed" and saved.source_hash == row.content_hash
            and saved.prompt_version == VISION_PROMPT_VERSION):
        return saved
    allowed, _, _ = await _daily_ai_budget(session, user.id)
    if not allowed:
        raise AppError("今日模型用量已达上限", code=4292, status_code=429)
    png = await asyncio.to_thread(safe_png, row)
    provider = None
    observations = None
    failure_kind = None
    try:
        async with _model_semaphore(), asyncio.timeout(settings.ai_workflow_timeout_seconds):
            provider = get_vision_provider()
            observations = validate_observations(await provider.observe(png))
    except httpx.HTTPStatusError as exc:
        failure_kind = f"provider_http_{exc.response.status_code}"
    except TimeoutError:
        failure_kind = "workflow_timeout"
    except httpx.TimeoutException:
        failure_kind = "provider_timeout"
    except httpx.NetworkError:
        failure_kind = "provider_network"
    except (ValueError, KeyError, TypeError):
        failure_kind = "configuration_or_invalid_output"
    except Exception:
        # Preserve OCR/source; never substitute fabricated vision descriptions.
        failure_kind = "vision_unavailable"
    usage = provider.combined_usage() if provider else None
    task = AnalysisTask(created_by=user.id, task_type="visual_review", progress=100,
                        status=TaskStatus.COMPLETED if observations else TaskStatus.FAILED,
                        completed_at=datetime.now(UTC), current_step="图片观察已保存"
                        if observations else "视觉模型不可用，保留本地OCR与原图",
                        input_snapshot={"projectVersionId": str(version_id),
                                        "sourceHash": row.content_hash,
                                        "promptVersion": VISION_PROMPT_VERSION,
                                        "model": provider.model if provider else None,
                                        "observations": observations.model_dump() if observations
                                        else None, "usage": usage.model_dump() if usage else None,
                                        "externalImageConsent": True, "reviewStatus": "pending"})
    task.input_snapshot = {**task.input_snapshot, "failureKind": failure_kind}
    session.add(task)
    await session.flush()
    if usage:
        session.add(AiUsageLog(analysis_task_id=task.id, model=provider.model,
                               input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                               cache_hit_tokens=usage.cache_hit_tokens, latency_ms=usage.latency_ms,
                               unit_price_snapshot={"provider": "zhipu", "priceVerified": False}))
    await session.commit()
    return view(task)


async def review_visual(session, review_id, request, user):
    task = await session.scalar(select(AnalysisTask).where(
        AnalysisTask.id == review_id, AnalysisTask.created_by == user.id,
        AnalysisTask.task_type == "visual_review").with_for_update())
    if not task or task.status != TaskStatus.COMPLETED:
        raise AppError("图片观察不存在或无权复核", code=4043, status_code=404)
    await owned_image(session, task.input_snapshot["projectVersionId"], user)
    task.input_snapshot = {**task.input_snapshot, "reviewStatus": request.status,
                           "reviewerNote": request.note, "reviewedAt": datetime.now(UTC).isoformat()
                           if request.status != "pending" else None}
    await session.commit()
    return view(task)


async def visual_attachments(session, version_ids, user):
    selected = set(map(str, version_ids))
    if not selected:
        return []
    tasks = await session.scalars(select(AnalysisTask).where(
        AnalysisTask.created_by == user.id, AnalysisTask.task_type == "visual_review",
        AnalysisTask.status == TaskStatus.COMPLETED,
        AnalysisTask.input_snapshot["projectVersionId"].as_string().in_(selected)
    ).order_by(AnalysisTask.created_at.desc()))
    seen = set()
    result = []
    for task in tasks:
        version = task.input_snapshot.get("projectVersionId")
        if version in selected and version not in seen:
            seen.add(version)
            result.append(view(task).model_dump(mode="json", by_alias=True))
    return result
