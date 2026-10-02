from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.identity import User
from app.schemas.common import ApiResponse, success
from app.schemas.evidence_growth import GrowthAnalyze, GrowthCreate, GrowthMaterials
from app.services.analysis import execute_match_task
from app.services.evidence_growth import EvidenceGrowthService
from app.services.task_runner import FastAPIBackgroundTaskRunner

router = APIRouter()


@router.post(
    "/match-reports/{report_id}/growth-tasks", response_model=ApiResponse[dict], status_code=201
)
async def create(
    report_id: UUID,
    payload: GrowthCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await EvidenceGrowthService(session).create(report_id, payload, user))


@router.get("/growth-tasks", response_model=ApiResponse[list[dict]])
async def list_tasks(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return success(await EvidenceGrowthService(session).list(user))


@router.get("/growth-tasks/{task_id}", response_model=ApiResponse[dict])
async def get(
    task_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await EvidenceGrowthService(session).get(task_id, user))


@router.put("/growth-tasks/{task_id}/materials", response_model=ApiResponse[dict])
async def attach(
    task_id: UUID,
    payload: GrowthMaterials,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await EvidenceGrowthService(session).attach(task_id, payload, user))


@router.post("/growth-tasks/{task_id}/analyze", response_model=ApiResponse[dict], status_code=202)
async def analyze(
    task_id: UUID,
    payload: GrowthAnalyze,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await EvidenceGrowthService(session).analyze(task_id, payload, user)
    if result["analysisStatus"] == "pending":
        FastAPIBackgroundTaskRunner().submit(
            background_tasks, execute_match_task, UUID(result["analysisTaskId"])
        )
    return success(result)


@router.get(
    "/match-reports/{report_id}/growth-tasks/{requirement_id}",
    response_model=ApiResponse[dict | None],
)
async def existing(
    report_id: UUID,
    requirement_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await EvidenceGrowthService(session).existing(report_id, requirement_id, user))


@router.get(
    "/match-reports/{report_id}/enterprise-replies/{requirement_id}",
    response_model=ApiResponse[dict | None],
)
async def enterprise_reply(
    report_id: UUID,
    requirement_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await EvidenceGrowthService(session).enterprise_reply(report_id, requirement_id, user)
    return success(result)
