import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.identity import User
from app.schemas.common import ApiResponse, success
from app.schemas.visual import VisualReviewRequest, VisualReviewUpdate, VisualReviewView
from app.services.visual_evidence import (
    latest_visual,
    observe_image,
    owned_image,
    review_visual,
    safe_png,
)

router = APIRouter()


@router.get("/project-versions/{version_id}/image")
async def image_source(version_id: UUID, user: User = Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    row = await owned_image(session, version_id, user)
    return Response(await asyncio.to_thread(safe_png, row), media_type="image/png",
                    headers={"Cache-Control": "private, no-store",
                             "X-Content-Type-Options": "nosniff"})


@router.get("/project-versions/{version_id}/visual-review",
            response_model=ApiResponse[VisualReviewView | None])
async def get_visual(version_id: UUID, user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    return success(await latest_visual(session, version_id, user))


@router.post("/project-versions/{version_id}/visual-review",
             response_model=ApiResponse[VisualReviewView])
async def create_visual(version_id: UUID, request: VisualReviewRequest,
                        user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    return success(await observe_image(session, version_id, request, user))


@router.patch("/visual-reviews/{review_id}", response_model=ApiResponse[VisualReviewView])
async def update_visual(review_id: UUID, request: VisualReviewUpdate,
                        user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    return success(await review_visual(session, review_id, request, user))
