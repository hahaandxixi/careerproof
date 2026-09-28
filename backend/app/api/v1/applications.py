from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.identity import User
from app.schemas.applications import ApplicationCreate, ApplicationReply
from app.schemas.common import ApiResponse, success
from app.services.applications import ApplicationService

router = APIRouter()


@router.post("/applications", response_model=ApiResponse[dict], status_code=201)
async def create(
    payload: ApplicationCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationService(session).create(payload, user))


@router.get("/applications/mine", response_model=ApiResponse[list[dict]])
async def mine(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return success(await ApplicationService(session).mine(user))


@router.get("/jobs/{job_id}/applications", response_model=ApiResponse[list[dict]])
async def candidates(
    job_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationService(session).candidates(job_id, user))


@router.post("/applications/{application_id}/view", response_model=ApiResponse[dict])
async def view(
    application_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ApplicationService(session).open(application_id, user))


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
