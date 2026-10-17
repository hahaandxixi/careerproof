from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import AppError
from app.models.identity import User
from app.schemas.common import ApiResponse, success
from app.services.notifications import NotificationService


def private_response(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/notifications", dependencies=[Depends(private_response)])


@router.get("", response_model=ApiResponse[dict])
async def listing(
    page: int = Query(1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=50, alias="pageSize"),
    page_size_legacy: int | None = Query(default=None, ge=1, le=50, alias="page_size"),
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # pageSize is canonical; page_size stays accepted for older clients. When a
    # caller sends both, equal values pass and a conflict must fail loudly rather
    # than silently pick one limit.
    if (
        page_size is not None
        and page_size_legacy is not None
        and page_size != page_size_legacy
    ):
        raise AppError("pageSize 与 page_size 冲突，请只使用 pageSize", status_code=422, code=4224)
    resolved = page_size if page_size is not None else page_size_legacy
    return success(
        await NotificationService(session).list(
            user, page, resolved if resolved is not None else 20, unread_only
        )
    )


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
