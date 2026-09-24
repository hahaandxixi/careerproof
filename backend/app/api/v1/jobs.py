from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import bearer, get_current_user
from app.core.database import get_session
from app.core.exceptions import AppError
from app.models.identity import User
from app.schemas.common import ApiResponse, PaginatedData, success
from app.schemas.jobs import (
    EmploymentType,
    JobCategory,
    JobCreate,
    JobDraftRequest,
    JobDraftResult,
    JobOptions,
    JobSummary,
    JobUpdate,
    JobView,
)
from app.services.job_drafting import draft_job_requirements
from app.services.jobs import JobService

router = APIRouter()


@router.post("/ai-draft", response_model=ApiResponse[JobDraftResult])
async def ai_draft_job_requirements(
    payload: JobDraftRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[JobDraftResult]:
    return success(await draft_job_requirements(session, payload, current_user))


async def optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    if not credentials and not request.cookies.get("careerproof_access"):
        return None
    try:
        return await get_current_user(request, credentials, session)
    except AppError as exc:
        if exc.status_code == 401:
            return None
        raise


@router.get("/options", response_model=ApiResponse[JobOptions])
async def job_options() -> ApiResponse[JobOptions]:
    return success(
        JobOptions(
            categories=[
                {"value": "software", "label": "软件开发"},
                {"value": "data_analysis", "label": "数据分析"},
                {"value": "operations", "label": "运营与策划"},
                {"value": "design", "label": "设计与创意"},
                {"value": "other", "label": "其他方向"},
            ],
            employment_types=[
                {"value": "internship", "label": "实习"},
                {"value": "campus", "label": "校园招聘"},
                {"value": "full_time", "label": "全职"},
            ],
            skills=[
                {"name": skill, "category": category}
                for category, skills in (
                    (
                        "software",
                        [
                            "Python",
                            "FastAPI",
                            "Java",
                            "TypeScript",
                            "React",
                            "PostgreSQL",
                            "MySQL",
                            "Redis",
                            "pytest",
                            "Docker",
                            "Git",
                            "Linux",
                        ],
                    ),
                    ("data_analysis", ["SQL", "数据清洗", "Excel", "统计分析", "数据可视化"]),
                    ("operations", ["用户调研", "活动策划", "内容运营"]),
                    ("design", ["用户研究", "交互设计", "视觉设计", "原型设计"]),
                    ("other", ["文案写作", "沟通表达", "项目管理"]),
                )
                for skill in skills
            ],
        )
    )


@router.get("/mine", response_model=ApiResponse[PaginatedData[JobSummary]])
async def my_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    category: JobCategory | None = None,
    city: str | None = Query(default=None, max_length=100),
    employment_type: EmploymentType | None = Query(default=None, alias="employmentType"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[JobSummary]]:
    return success(
        await JobService(session).list(
            page,
            page_size,
            current_user=current_user,
            mine=True,
            q=q,
            category=category,
            city=city,
            employment_type=employment_type,
        )
    )


@router.get("", response_model=ApiResponse[PaginatedData[JobSummary]])
async def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    category: JobCategory | None = None,
    city: str | None = Query(default=None, max_length=100),
    employment_type: EmploymentType | None = Query(default=None, alias="employmentType"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[JobSummary]]:
    return success(
        await JobService(session).list(
            page,
            page_size,
            q=q,
            category=category,
            city=city,
            employment_type=employment_type,
        )
    )


@router.get("/{job_id}", response_model=ApiResponse[JobView])
async def get_job(
    job_id: UUID,
    current_user: User | None = Depends(optional_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[JobView]:
    return success(await JobService(session).get(job_id, current_user))


@router.post("", response_model=ApiResponse[JobView], status_code=201)
async def create_job(
    payload: JobCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[JobView]:
    return success(await JobService(session).create(payload, current_user), message="created")


@router.patch("/{job_id}", response_model=ApiResponse[JobView])
async def update_job(
    job_id: UUID,
    payload: JobUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[JobView]:
    return success(await JobService(session).update(job_id, payload, current_user))
