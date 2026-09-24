from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_session
from app.models.identity import User
from app.schemas.common import ApiResponse, success
from app.schemas.portfolio import (
    KnowledgeSearchResult,
    MaterialVersionView,
    ProjectCreate,
    ProjectFilePreview,
    ProjectFileView,
    ProjectHistoryView,
    ProjectVersionUploadData,
    ProjectView,
    ResumeHistoryView,
    ResumePreview,
    ResumeUploadData,
)
from app.services.portfolio import (
    RESUME_MAX_BYTES,
    PortfolioService,
    execute_project_scan_task,
    execute_resume_parse_task,
)
from app.services.retrieval import search_owned_chunks
from app.services.task_runner import FastAPIBackgroundTaskRunner

router = APIRouter()


@router.get("/knowledge/search", response_model=ApiResponse[list[KnowledgeSearchResult]])
async def search_knowledge(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=8, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[KnowledgeSearchResult]]:
    return success(await search_owned_chunks(session, current_user, q, limit))


@router.get("/resume-versions/{version_id}/preview", response_model=ApiResponse[ResumePreview])
async def preview_resume(
    version_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ResumePreview]:
    return success(await PortfolioService(session).preview_resume(version_id, current_user))


@router.get(
    "/project-versions/{version_id}/files", response_model=ApiResponse[list[ProjectFileView]]
)
async def project_files(
    version_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[ProjectFileView]]:
    return success(await PortfolioService(session).list_project_files(version_id, current_user))


@router.get("/project-files/{file_id}", response_model=ApiResponse[ProjectFilePreview])
async def preview_project_file(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectFilePreview]:
    return success(await PortfolioService(session).preview_project_file(file_id, current_user))


@router.get("/resumes", response_model=ApiResponse[list[ResumeHistoryView]])
async def list_resumes(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[ResumeHistoryView]]:
    return success(await PortfolioService(session).list_resumes(current_user))


@router.get("/resumes/{resume_id}/versions", response_model=ApiResponse[list[MaterialVersionView]])
async def list_resume_versions(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[MaterialVersionView]]:
    return success(await PortfolioService(session).list_resume_versions(resume_id, current_user))


@router.get("/projects", response_model=ApiResponse[list[ProjectHistoryView]])
async def list_projects(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[ProjectHistoryView]]:
    return success(await PortfolioService(session).list_projects(current_user))


@router.get(
    "/projects/{project_id}/versions", response_model=ApiResponse[list[MaterialVersionView]]
)
async def list_project_versions(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[MaterialVersionView]]:
    return success(await PortfolioService(session).list_project_versions(project_id, current_user))


@router.post("/resumes", response_model=ApiResponse[ResumeUploadData], status_code=202)
async def upload_resume(
    background_tasks: BackgroundTasks,
    title: str = Form(min_length=1, max_length=200),
    file: UploadFile = File(),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ResumeUploadData]:
    content = await file.read(RESUME_MAX_BYTES + 1)
    accepted = await PortfolioService(session).create_resume_upload(
        title=title,
        filename=file.filename or "resume",
        mime_type=file.content_type or "application/octet-stream",
        content=content,
        current_user=current_user,
    )
    FastAPIBackgroundTaskRunner().submit(
        background_tasks,
        execute_resume_parse_task,
        accepted.task_id,
        accepted.version_id,
    )
    return success(accepted, message="accepted")


@router.post("/projects", response_model=ApiResponse[ProjectView], status_code=201)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectView]:
    return success(
        await PortfolioService(session).create_project(payload, current_user),
        message="created",
    )


@router.post(
    "/projects/{project_id}/versions",
    response_model=ApiResponse[ProjectVersionUploadData],
    status_code=202,
)
async def upload_project_version(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(),
    request_id: UUID | None = Form(default=None, alias="requestId"),
    material_role: Literal["portfolio", "reference"] = Form(
        default="portfolio", alias="materialRole"
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectVersionUploadData]:
    content = await file.read(settings.max_archive_bytes + 1)
    accepted, created = await PortfolioService(session).create_project_version(
        project_id=project_id,
        filename=file.filename or "project.zip",
        content=content,
        current_user=current_user,
        request_id=request_id,
        material_role=material_role,
    )
    if created:
        FastAPIBackgroundTaskRunner().submit(
            background_tasks,
            execute_project_scan_task,
            accepted.task_id,
            accepted.version_id,
        )
    return success(accepted, message="accepted")
