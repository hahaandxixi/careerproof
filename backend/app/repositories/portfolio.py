from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisTask
from app.models.identity import StudentProfile
from app.models.portfolio import (
    Project,
    ProjectFile,
    ProjectVersion,
    Resume,
    ResumeSection,
    ResumeVersion,
)


class PortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def student_by_user(self, user_id: UUID) -> StudentProfile | None:
        result = await self.session.execute(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_project(self, project_id: UUID) -> Project | None:
        return await self.session.get(Project, project_id)

    async def owned_project(
        self, project_id: UUID, student_id: UUID, *, lock: bool = False
    ) -> Project | None:
        query = select(Project).where(Project.id == project_id, Project.student_id == student_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def owned_resume(self, resume_id: UUID, student_id: UUID) -> Resume | None:
        return await self.session.scalar(
            select(Resume).where(Resume.id == resume_id, Resume.student_id == student_id)
        )

    async def project_by_request(self, student_id: UUID, request_id: UUID) -> Project | None:
        return await self.session.scalar(
            select(Project).where(
                Project.student_id == student_id,
                Project.create_request_id == request_id,
            )
        )

    async def version_by_request(self, project_id: UUID, request_id: UUID) -> ProjectVersion | None:
        return await self.session.scalar(
            select(ProjectVersion).where(
                ProjectVersion.project_id == project_id,
                ProjectVersion.upload_request_id == request_id,
            )
        )

    async def list_resumes(self, student_id: UUID, include_archived: bool = False) -> list[Resume]:
        return list(
            await self.session.scalars(
                select(Resume)
                .where(
                    Resume.student_id == student_id,
                    True if include_archived else Resume.is_archived.is_(False),
                )
                .order_by(Resume.created_at.desc(), Resume.id)
            )
        )

    async def list_projects(
        self, student_id: UUID, include_archived: bool = False
    ) -> list[Project]:
        return list(
            await self.session.scalars(
                select(Project)
                .where(
                    Project.student_id == student_id,
                    True if include_archived else Project.is_archived.is_(False),
                )
                .order_by(Project.created_at.desc(), Project.id)
            )
        )

    async def resume_versions(self, student_id: UUID, resume_id: UUID | None = None):
        query = (
            select(ResumeVersion, AnalysisTask)
            .join(Resume)
            .outerjoin(
                AnalysisTask,
                ResumeVersion.analysis_task_id == AnalysisTask.id,
            )
            .where(Resume.student_id == student_id)
        )
        if resume_id:
            query = query.where(ResumeVersion.resume_id == resume_id)
        return (
            await self.session.execute(
                query.order_by(
                    ResumeVersion.version_number.desc(),
                    ResumeVersion.id,
                )
            )
        ).all()

    async def project_versions(self, student_id: UUID, project_id: UUID | None = None):
        query = (
            select(ProjectVersion, AnalysisTask)
            .join(Project)
            .outerjoin(
                AnalysisTask,
                ProjectVersion.analysis_task_id == AnalysisTask.id,
            )
            .where(Project.student_id == student_id)
        )
        if project_id:
            query = query.where(ProjectVersion.project_id == project_id)
        return (
            await self.session.execute(
                query.order_by(
                    ProjectVersion.version_number.desc(),
                    ProjectVersion.id,
                )
            )
        ).all()

    async def next_project_version(self, project_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.max(ProjectVersion.version_number)).where(
                ProjectVersion.project_id == project_id
            )
        )
        return int(value or 0) + 1

    async def owned_resume_version(self, version_id: UUID, student_id: UUID):
        return await self.session.scalar(
            select(ResumeVersion)
            .join(Resume)
            .where(ResumeVersion.id == version_id, Resume.student_id == student_id)
        )

    async def owned_project_version(self, version_id: UUID, student_id: UUID):
        return await self.session.scalar(
            select(ProjectVersion)
            .join(Project)
            .where(ProjectVersion.id == version_id, Project.student_id == student_id)
        )

    async def owned_project_file(self, file_id: UUID, student_id: UUID):
        return await self.session.scalar(
            select(ProjectFile)
            .join(ProjectVersion)
            .join(Project)
            .where(ProjectFile.id == file_id, Project.student_id == student_id)
        )

    async def sections(self, version_id: UUID) -> list[ResumeSection]:
        return list(
            await self.session.scalars(
                select(ResumeSection)
                .where(ResumeSection.resume_version_id == version_id)
                .order_by(ResumeSection.page_number, ResumeSection.created_at, ResumeSection.id)
            )
        )

    async def files(self, version_id: UUID) -> list[ProjectFile]:
        return list(
            await self.session.scalars(
                select(ProjectFile)
                .where(ProjectFile.project_version_id == version_id)
                .order_by(ProjectFile.relative_path)
            )
        )

    def add_resume(self, resume: Resume, version: ResumeVersion) -> None:
        self.session.add(resume)
        self.session.add(version)

    def add_project(self, project: Project) -> None:
        self.session.add(project)

    def add_project_version(self, version: ProjectVersion) -> None:
        self.session.add(version)

    def add_resume_sections(self, sections: list[ResumeSection]) -> None:
        self.session.add_all(sections)

    def add_project_files(self, files: list[ProjectFile]) -> None:
        self.session.add_all(files)
