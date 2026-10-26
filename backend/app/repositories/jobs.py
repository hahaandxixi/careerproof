from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import MembershipRole
from app.models.identity import Enterprise, EnterpriseMembership
from app.models.recruitment import Job, JobRequirement, Skill
from app.tools.technical_careers import discovery_conditions


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
        direction: str | None = None,
        specialty: str | None = None,
        language: str | None = None,
        manager_id: UUID | None = None,
        include_all: bool = False,
    ) -> tuple[list[tuple[Job, int]], int]:
        conditions = []
        if manager_id is not None:
            conditions.append(Job.enterprise_id.in_(self.managed_enterprise_ids(manager_id)))
        elif not include_all:
            # Discovery (and only discovery): published, and explicitly visible. Count and
            # slice share these conditions, so a hidden posting is neither counted nor
            # paged into a gap. Management listings above stay unfiltered.
            conditions.append(Job.status == "published")
            conditions.append(Job.discovery_visible.is_(True))
        if q:
            conditions.append(
                or_(
                    Job.title.icontains(q, autoescape=True),
                    Job.company_name.icontains(q, autoescape=True),
                    Job.description.icontains(q, autoescape=True),
                    exists(select(1).where(
                        JobRequirement.job_id == Job.id,
                        or_(JobRequirement.skill_name.icontains(q, autoescape=True),
                            JobRequirement.raw_text.icontains(q, autoescape=True)),
                    ).correlate(Job)),
                )
            )
        if category:
            conditions.append(Job.category == category)
        if city:
            conditions.append(Job.city == city)
        if employment_type:
            conditions.append(Job.employment_type == employment_type)
        conditions.extend(discovery_conditions(direction, specialty, language))
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

    async def recommendation_candidates(self, limit: int) -> list[Job]:
        """Published jobs that may be recommended — the same visibility predicate as discovery."""
        return list(
            await self.session.scalars(
                select(Job)
                .where(Job.status == "published", Job.discovery_visible.is_(True))
                .order_by(Job.created_at.desc(), Job.id.desc())
                .limit(limit)
            )
        )

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
