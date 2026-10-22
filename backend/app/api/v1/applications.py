from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.identity import User
from app.schemas.application_verification import ApplicationVerificationRequest
from app.schemas.applications import ApplicationCreate, ApplicationReply
from app.schemas.common import ApiResponse, PaginatedData, success
from app.services.application_verification import (
    ApplicationVerificationService,
    execute_application_verification_task,
)
from app.services.applications import ApplicationService
from app.services.task_runner import FastAPIBackgroundTaskRunner

router = APIRouter()


@router.post("/applications", response_model=ApiResponse[dict], status_code=201)
async def create(
    payload: ApplicationCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationService(session).create(payload, user))


@router.get("/applications/mine", response_model=ApiResponse[PaginatedData[dict]])
async def mine(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    job_id: UUID | None = Query(default=None, alias="jobId"),
    q: str | None = Query(default=None, max_length=200),
    view: Literal["all", "waiting", "action", "withdrawn"] = "all",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationService(session).mine(
        user, page, page_size, job_id, q=q, view=view,
    ))


@router.get("/jobs/{job_id}/applications", response_model=ApiResponse[PaginatedData[dict]])
async def candidates(
    job_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    q: str | None = Query(default=None, max_length=200),
    status: Literal["submitted", "viewed", "downloaded", "replied"] | None = None,
    requirement_id: UUID | None = Query(default=None, alias="requirementId"),
    verdict: Literal["supported", "claimed_only", "gap", "unsupported"] | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationService(session).candidates(
        job_id, user, page, page_size, q=q, status=status,
        requirement_id=requirement_id, verdict=verdict,
    ))


@router.get("/applications/{application_id}", response_model=ApiResponse[dict])
async def detail(
    application_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    response.headers["Cache-Control"] = "private, no-store"
    return success(await ApplicationService(session).detail(application_id, user))


@router.post("/applications/{application_id}/view", response_model=ApiResponse[dict])
async def view(
    application_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationService(session).open(application_id, user))


@router.post(
    "/applications/{application_id}/verification", response_model=ApiResponse[dict], status_code=202
)
async def create_verification(
    application_id: UUID,
    payload: ApplicationVerificationRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await ApplicationVerificationService(session).create(application_id, payload, user)
    if result["status"] == "pending" and not result["reused"]:
        FastAPIBackgroundTaskRunner().submit(
            background_tasks, execute_application_verification_task, UUID(result["taskId"])
        )
    return success(result, message="accepted")


@router.get("/applications/{application_id}/verification", response_model=ApiResponse[dict | None])
async def latest_verification(
    application_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationVerificationService(session).latest(application_id, user))


@router.get(
    "/applications/{application_id}/verification/{task_id}", response_model=ApiResponse[dict]
)
async def get_verification(
    application_id: UUID,
    task_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationVerificationService(session).get(application_id, task_id, user))


@router.post("/applications/{application_id}/reply", response_model=ApiResponse[dict])
async def reply(
    application_id: UUID,
    payload: ApplicationReply,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationService(session).reply(application_id, payload, user))


@router.post("/applications/{application_id}/withdraw", response_model=ApiResponse[dict])
async def withdraw(
    application_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationService(session).withdraw(application_id, user))


@router.post("/applications/{application_id}/resume-download")
async def download(
    application_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    content, mime, filename = await ApplicationService(session).download(application_id, user)
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
