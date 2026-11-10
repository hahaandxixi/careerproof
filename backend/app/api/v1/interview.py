from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.identity import User
from app.schemas.common import ApiResponse, success
from app.schemas.interview import (
    InterviewAnswerRequest,
    InterviewSessionCreate,
    InterviewSessionEnvelope,
    InterviewSessionView,
    InterviewStartRequest,
)
from app.services.interview_practice import InterviewPracticeService

router = APIRouter()


def _envelope(view: dict, resumed: bool = False) -> InterviewSessionEnvelope:
    return InterviewSessionEnvelope(
        session=InterviewSessionView.model_validate(view), resumed=resumed
    )


@router.post(
    "/match-reports/{report_id}/interview-sessions",
    response_model=ApiResponse[InterviewSessionEnvelope],
)
async def create_interview_session(
    report_id: UUID,
    payload: InterviewSessionCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[InterviewSessionEnvelope]:
    """Open (or resume) the practice bound to one saved report requirement.

    Creating a session never calls the model and never sends material.
    """
    service = InterviewPracticeService(session)
    row, resumed = await service.create_or_resume(
        report_id, payload.requirement_id, current_user, restart=payload.restart
    )
    return success(_envelope(await service.view(row.id, current_user), resumed))


@router.get(
    "/interview-sessions/{session_id}",
    response_model=ApiResponse[InterviewSessionView],
)
async def get_interview_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[InterviewSessionView]:
    view = await InterviewPracticeService(session).view(session_id, current_user)
    return success(InterviewSessionView.model_validate(view))


@router.post(
    "/interview-sessions/{session_id}/start",
    response_model=ApiResponse[InterviewSessionView],
)
async def start_interview_session(
    session_id: UUID,
    payload: InterviewStartRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[InterviewSessionView]:
    service = InterviewPracticeService(session)
    await service.start(session_id, current_user, consent=payload.external_ai_consent)
    view = await service.view(session_id, current_user)
    return success(InterviewSessionView.model_validate(view))


@router.post(
    "/interview-sessions/{session_id}/turns/{turn_index}/answers",
    response_model=ApiResponse[InterviewSessionView],
)
async def submit_interview_answer(
    session_id: UUID,
    turn_index: int,
    payload: InterviewAnswerRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[InterviewSessionView]:
    service = InterviewPracticeService(session)
    await service.submit_answer(
        session_id, turn_index, payload.answer_text, payload.client_token, current_user
    )
    view = await service.view(session_id, current_user)
    return success(InterviewSessionView.model_validate(view))


@router.post(
    "/interview-sessions/{session_id}/turns/{turn_index}/retry",
    response_model=ApiResponse[InterviewSessionView],
)
async def retry_interview_feedback(
    session_id: UUID,
    turn_index: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[InterviewSessionView]:
    """Retry only after the client re-read the saved state; never re-asks a question."""
    service = InterviewPracticeService(session)
    await service.retry_feedback(session_id, turn_index, current_user)
    view = await service.view(session_id, current_user)
    return success(InterviewSessionView.model_validate(view))
