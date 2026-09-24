from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.enums import UserRole
from app.models.identity import User
from app.models.recruitment import Job, JobRequirement
from app.repositories.jobs import JobRepository
from app.schemas.common import PaginatedData
from app.schemas.jobs import (
    JobCreate,
    JobRequirementView,
    JobSummary,
    JobUpdate,
    JobView,
)


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = JobRepository(session)

    async def list(
        self,
        page: int,
        page_size: int,
        *,
        current_user: User | None = None,
        mine: bool = False,
        **filters,
    ) -> PaginatedData[JobSummary]:
        if mine and (
            current_user is None or current_user.role not in {UserRole.ENTERPRISE, UserRole.ADMIN}
        ):
            raise AppError("只有企业用户可以管理岗位", code=4033, status_code=403)
        admin = bool(mine and current_user and current_user.role == UserRole.ADMIN)
        rows, total = await self.jobs.list(
            page=page,
            page_size=page_size,
            manager_id=current_user.id if mine and not admin else None,
            include_all=admin,
            **filters,
        )
        return PaginatedData(
            items=[
                JobSummary(
                    id=job.id,
                    title=job.title,
                    company_name=job.company_name,
                    description=job.description,
                    status=job.status,
                    category=job.category,
                    city=job.city,
                    employment_type=job.employment_type,
                    requirement_count=requirement_count,
                    created_at=job.created_at,
                )
                for job, requirement_count in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get(self, job_id: UUID, current_user: User | None = None) -> JobView:
        job = await self.jobs.get(job_id)
        if not job:
            raise AppError("岗位不存在", code=4040, status_code=404)
        if job.status != "published" and not await self.can_manage(job, current_user):
            raise AppError("岗位不存在或尚未公开", code=4040, status_code=404)
        requirements = await self.jobs.requirements(job_id)
        return self._view(job, requirements)

    async def create(self, request: JobCreate, current_user: User) -> JobView:
        if current_user.role not in {UserRole.ENTERPRISE, UserRole.ADMIN}:
            raise AppError("只有企业用户可以发布岗位", code=4033, status_code=403)
        enterprise = await self.jobs.managed_enterprise(request.enterprise_id, current_user.id)
        if enterprise is None:
            raise AppError("请选择您担任负责人或HR的有效企业组织", code=4034, status_code=403)
        self._validate_requirement_sources(request.description, request.requirements)
        await self._validate_skills(request.requirements)
        job = Job(
            enterprise_id=request.enterprise_id,
            created_by=current_user.id,
            title=request.title,
            company_name=enterprise.name,
            description=request.description,
            status=request.status,
            category=request.category,
            city=request.city,
            employment_type=request.employment_type,
        )
        self.jobs.add_job(job)
        await self.session.flush()
        requirements = self._requirements(job.id, request.requirements)
        self.jobs.add_requirements(requirements)
        await self.session.commit()
        return self._view(job, requirements)

    async def can_manage(self, job: Job, user: User | None) -> bool:
        if user is None:
            return False
        if user.role == UserRole.ADMIN:
            return True
        if user.role != UserRole.ENTERPRISE:
            return False
        return await self.jobs.managed_enterprise(job.enterprise_id, user.id) is not None

    async def update(self, job_id: UUID, request: JobUpdate, current_user: User) -> JobView:
        # Matching task creation takes the same row lock before saving requirement IDs.
        job = await self.jobs.get(job_id, lock=True)
        if job is None or not await self.can_manage(job, current_user):
            raise AppError("岗位不存在或无管理权限", code=4040, status_code=404)
        values = request.model_dump(exclude_unset=True)
        if any(value is None for value in values.values()):
            raise AppError("岗位字段不能设为空值", code=4221, status_code=422)
        requirements = await self.jobs.requirements(job.id)
        effective_description = values.get("description", job.description)
        self._validate_requirement_sources(
            effective_description,
            request.requirements if request.requirements is not None else requirements,
        )
        if "requirements" in values:
            old = [
                {
                    key: getattr(item, key)
                    for key in (
                        "raw_text", "skill_name", "skill_id", "weight", "is_required",
                        "source_quote", "source_start", "source_end",
                    )
                }
                for item in requirements
            ]
            values.pop("requirements")
            new = [item.model_dump() for item in request.requirements]
            if old != new:
                if await self.jobs.has_matching_history(job.id):
                    raise AppError(
                        "岗位已有匹配任务或报告，要求已锁定；请新建岗位以调整要求",
                        code=4095,
                        status_code=409,
                    )
                await self._validate_skills(request.requirements)
                await self.jobs.delete_requirements(job.id)
                requirements = self._requirements(job.id, request.requirements)
                self.jobs.add_requirements(requirements)
        for field, value in values.items():
            setattr(job, field, value)
        job.version += 1
        await self.session.commit()
        return self._view(job, requirements)

    async def _validate_skills(self, requirements) -> None:
        skill_ids = {item.skill_id for item in requirements if item.skill_id is not None}
        if not await self.jobs.skill_ids_exist(skill_ids):
            raise AppError("技能ID不存在，请使用技能名称或有效ID", code=4222, status_code=422)

    @staticmethod
    def _validate_requirement_sources(description: str, requirements) -> None:
        for item in requirements:
            quote = item.source_quote
            start = item.source_start
            end = item.source_end
            if quote is None and start is None and end is None:
                continue
            if (
                quote is None or start is None or end is None or start >= end
                or description[start:end] != quote
            ):
                raise AppError(
                    "AI要求的原文定位已失效，请重新拆解或清除该条来源后手动确认",
                    code=4226,
                    status_code=422,
                )

    @staticmethod
    def _requirements(job_id: UUID, items) -> list[JobRequirement]:
        return [
            JobRequirement(
                job_id=job_id,
                skill_id=item.skill_id,
                raw_text=item.raw_text,
                skill_name=item.skill_name,
                weight=item.weight,
                is_required=item.is_required,
                normalized_status="normalized" if item.skill_id else "pending",
                source_quote=item.source_quote,
                source_start=item.source_start,
                source_end=item.source_end,
            )
            for item in items
        ]

    @staticmethod
    def _view(job: Job, requirements: list[JobRequirement]) -> JobView:
        return JobView(
            id=job.id,
            enterprise_id=job.enterprise_id,
            created_by=job.created_by,
            title=job.title,
            company_name=job.company_name,
            description=job.description,
            status=job.status,
            category=job.category,
            city=job.city,
            employment_type=job.employment_type,
            created_at=job.created_at,
            requirements=[JobRequirementView.model_validate(item) for item in requirements],
        )
