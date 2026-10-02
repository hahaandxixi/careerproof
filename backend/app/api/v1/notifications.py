from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.identity import User
from app.schemas.common import ApiResponse, success
from app.services.notifications import NotificationService


def private_response(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/notifications", dependencies=[Depends(private_response)])


@router.get("", response_model=ApiResponse[dict])
async def listing(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await NotificationService(session).list(user, page, page_size, unread_only))


@router.get("/unread-count", response_model=ApiResponse[dict])
async def count(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return success({"unreadCount": await NotificationService(session).count(user)})


@router.post("/read-all", response_model=ApiResponse[dict])
async def read_all(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return success(await NotificationService(session).read_all(user))


@router.post("/{notification_id}/read", response_model=ApiResponse[dict])
async def read(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await NotificationService(session).read(notification_id, user))


@router.get("/{notification_id}/target", response_model=ApiResponse[dict])
async def target(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await NotificationService(session).target(notification_id, user))
