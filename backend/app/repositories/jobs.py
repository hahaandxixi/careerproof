from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import MembershipRole
from app.models.identity import Enterprise, EnterpriseMembership
from app.models.recruitment import Job, JobRequirement, Skill


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        q: str | None = None,
        category: str | None = None,
        city: str | None = None,
        employment_type: str | None = None,
        manager_id: UUID | None = None,
        include_all: bool = False,
    ) -> tuple[list[tuple[Job, int]], int]:
        conditions = []
        if manager_id is not None:
            conditions.append(Job.enterprise_id.in_(self.managed_enterprise_ids(manager_id)))
        elif not include_all:
            conditions.append(Job.status == "published")
        if q:
            conditions.append(
                or_(
                    Job.title.icontains(q, autoescape=True),
                    Job.company_name.icontains(q, autoescape=True),
                    Job.description.icontains(q, autoescape=True),
                )
            )
        if category:
            conditions.append(Job.category == category)
        if city:
            conditions.append(Job.city == city)
        if employment_type:
            conditions.append(Job.employment_type == employment_type)
        count_result = await self.session.scalar(
            select(func.count()).select_from(Job).where(*conditions)
        )
        query = (
            select(Job, func.count(JobRequirement.id))
            .outerjoin(JobRequirement, JobRequirement.job_id == Job.id)
            .where(*conditions)
            .group_by(Job.id)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await self.session.execute(query)).all())
        return rows, int(count_result or 0)

    async def get(self, job_id: UUID, *, lock: bool = False) -> Job | None:
        query = select(Job).where(Job.id == job_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    @staticmethod
    def managed_enterprise_ids(user_id: UUID):
        return select(EnterpriseMembership.enterprise_id).where(
            EnterpriseMembership.user_id == user_id,
            EnterpriseMembership.is_active.is_(True),
            EnterpriseMembership.role.in_([MembershipRole.OWNER, MembershipRole.HR]),
        )

    async def managed_enterprise(
        self, enterprise_id: UUID | None, user_id: UUID
    ) -> Enterprise | None:
        if enterprise_id is None:
            return None
        return await self.session.scalar(
            select(Enterprise).where(
                Enterprise.id == enterprise_id,
                Enterprise.id.in_(self.managed_enterprise_ids(user_id)),
            )
        )

    async def skill_ids_exist(self, skill_ids: set[UUID]) -> bool:
        if not skill_ids:
            return True
        count = await self.session.scalar(
            select(func.count()).select_from(Skill).where(Skill.id.in_(skill_ids))
        )
        return count == len(skill_ids)

    async def has_matching_history(self, job_id: UUID) -> bool:
        if await self.session.scalar(select(MatchReport.id).where(MatchReport.job_id == job_id)):
            return True
        return (
            await self.session.scalar(
                select(AnalysisTask.id)
                .where(
                    AnalysisTask.task_type == "job_match",
                    AnalysisTask.input_snapshot["jobId"].as_string() == str(job_id),
                )
                .limit(1)
            )
        ) is not None

    async def delete_requirements(self, job_id: UUID) -> None:
        await self.session.execute(delete(JobRequirement).where(JobRequirement.job_id == job_id))

    async def requirements(self, job_id: UUID) -> list[JobRequirement]:
        result = await self.session.execute(
            select(JobRequirement)
            .where(JobRequirement.job_id == job_id)
            .order_by(JobRequirement.created_at)
        )
        return list(result.scalars().all())

    def add_job(self, job: Job) -> None:
        self.session.add(job)

    def add_requirements(self, requirements: list[JobRequirement]) -> None:
        self.session.add_all(requirements)
