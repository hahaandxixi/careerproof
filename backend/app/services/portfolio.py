from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import suppress
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import AppError
from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus, UserRole
from app.models.identity import User
from app.models.portfolio import (
    Project,
    ProjectFile,
    ProjectVersion,
    Resume,
    ResumeSection,
    ResumeVersion,
)
from app.repositories.analysis import AnalysisRepository
from app.repositories.portfolio import PortfolioRepository
from app.schemas.analysis import TaskAccepted
from app.schemas.portfolio import (
    MaterialVersionView,
    ProjectCreate,
    ProjectFilePreview,
    ProjectFileView,
    ProjectHistoryView,
    ProjectVersionUploadData,
    ProjectView,
    ResumeHistoryView,
    ResumePreview,
    ResumeSectionView,
    ResumeUploadData,
)
from app.services.retrieval import ChunkSource, delete_source_chunks, index_sources
from app.services.task_lifecycle import claim_task, finish_task, heartbeat_task, reset_failed_task
from app.services.task_runner import run_isolated
from app.tools.archive_scanner import ArchiveLimits
from app.tools.material_processor import process_document, process_project
from app.tools.storage import LocalStorage

RESUME_MAX_BYTES = 10 * 1024 * 1024


class PortfolioService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.portfolios = PortfolioRepository(session)
        self.analysis = AnalysisRepository(session)
        self.storage = LocalStorage(settings.storage_base_dir)

    @staticmethod
    def _version_view(
        version: ResumeVersion | ProjectVersion, task: AnalysisTask | None
    ) -> MaterialVersionView:
        status = (
            version.parse_status if isinstance(version, ResumeVersion) else version.analysis_status
        )
        return MaterialVersionView(
            id=version.id,
            version_number=version.version_number,
            original_filename=version.original_filename,
            size_bytes=version.size_bytes,
            created_at=version.created_at,
            status=task.status.value if task else status,
            task_id=version.analysis_task_id,
            progress=task.progress if task else (100 if status == "completed" else None),
            current_step=task.current_step if task else None,
            error_message=task.error_message if task else None,
        )

    async def list_resumes(self, current_user: User) -> list[ResumeHistoryView]:
        student = await self._student(current_user)
        resumes = await self.portfolios.list_resumes(student.id)
        versions: dict[UUID, list[MaterialVersionView]] = {}
        for version, task in await self.portfolios.resume_versions(student.id):
            versions.setdefault(version.resume_id, []).append(self._version_view(version, task))
        return [
            ResumeHistoryView(
                id=item.id,
                title=item.title,
                created_at=item.created_at,
                versions=versions.get(item.id, []),
            )
            for item in resumes
        ]

    async def list_projects(self, current_user: User) -> list[ProjectHistoryView]:
        student = await self._student(current_user)
        projects = await self.portfolios.list_projects(student.id)
        versions: dict[UUID, list[MaterialVersionView]] = {}
        for version, task in await self.portfolios.project_versions(student.id):
            versions.setdefault(version.project_id, []).append(self._version_view(version, task))
        return [
            ProjectHistoryView(
                id=item.id,
                name=item.name,
                description=item.description,
                version=item.version,
                created_at=item.created_at,
                versions=versions.get(item.id, []),
            )
            for item in projects
        ]

    async def list_resume_versions(
        self, resume_id: UUID, current_user: User
    ) -> list[MaterialVersionView]:
        student = await self._student(current_user)
        if not await self.portfolios.owned_resume(resume_id, student.id):
            raise AppError("简历不存在或无权访问", code=4045, status_code=404)
        return [
            self._version_view(version, task)
            for version, task in await self.portfolios.resume_versions(student.id, resume_id)
        ]

    async def list_project_versions(
        self, project_id: UUID, current_user: User
    ) -> list[MaterialVersionView]:
        student = await self._student(current_user)
        if not await self.portfolios.owned_project(project_id, student.id):
            raise AppError("项目不存在或无权访问", code=4043, status_code=404)
        return [
            self._version_view(version, task)
            for version, task in await self.portfolios.project_versions(student.id, project_id)
        ]

    async def create_resume_upload(
        self,
        *,
        title: str,
        filename: str,
        mime_type: str,
        content: bytes,
        current_user: User,
    ) -> ResumeUploadData:
        student = await self._student(current_user)
        if len(content) > RESUME_MAX_BYTES:
            raise AppError("简历文件不得超过10MB", code=4021, status_code=413)
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            raise AppError(
                "仅支持PDF、DOCX、TXT、PNG、JPG、WEBP或BMP简历",
                code=4020,
                status_code=415,
            )
        resume = Resume(student_id=student.id, title=title)
        self.session.add(resume)
        await self.session.flush()
        content_hash = hashlib.sha256(content).hexdigest()
        version = ResumeVersion(
            resume_id=resume.id,
            version_number=1,
            storage_key="",
            content_hash=content_hash,
            mime_type=mime_type,
            size_bytes=len(content),
            parse_status="pending",
            original_filename=Path(filename.replace("\\", "/")).name[:255],
        )
        self.session.add(version)
        await self.session.flush()
        object_key = f"resumes/{resume.id}/{version.id}{suffix}"
        self.storage.save(object_key, content)
        version.storage_key = object_key
        task = AnalysisTask(
            created_by=current_user.id,
            task_type="resume_parse",
            status=TaskStatus.PENDING,
            current_step="等待解析",
        )
        self.analysis.add_task(task)
        await self.session.flush()
        version.analysis_task_id = task.id
        await self.session.commit()
        return ResumeUploadData(
            resume_id=resume.id,
            version_id=version.id,
            task_id=task.id,
            status=task.status,
        )

    async def preview_resume(self, version_id: UUID, current_user: User) -> ResumePreview:
        student = await self._student(current_user)
        version = await self.portfolios.owned_resume_version(version_id, student.id)
        if not version:
            raise AppError("简历版本不存在或无权访问", code=4045, status_code=404)
        return ResumePreview(
            id=version.id,
            status=version.parse_status,
            sections=[
                ResumeSectionView.model_validate(item)
                for item in await self.portfolios.sections(version.id)
            ],
        )

    async def list_project_files(
        self, version_id: UUID, current_user: User
    ) -> list[ProjectFileView]:
        student = await self._student(current_user)
        if not await self.portfolios.owned_project_version(version_id, student.id):
            raise AppError("项目版本不存在或无权访问", code=4043, status_code=404)
        return [
            ProjectFileView.model_validate(item) for item in await self.portfolios.files(version_id)
        ]

    async def preview_project_file(self, file_id: UUID, current_user: User) -> ProjectFilePreview:
        student = await self._student(current_user)
        file = await self.portfolios.owned_project_file(file_id, student.id)
        if not file:
            raise AppError("项目文件不存在或无权访问", code=4043, status_code=404)
        try:
            content = await asyncio.to_thread(self.storage.resolve(file.storage_key).read_bytes)
        except (OSError, ValueError) as exc:
            raise AppError("文件暂不可用，请重新上传材料", code=4046, status_code=404) from exc
        return ProjectFilePreview(
            id=file.id,
            relative_path=file.relative_path,
            content=content.decode("utf-8", errors="replace"),
            project_version_id=file.project_version_id,
        )

    async def create_project(self, payload: ProjectCreate, current_user: User) -> ProjectView:
        student = await self._student(current_user)
        student_id = student.id
        fingerprint = hashlib.sha256(
            json.dumps(
                {"name": payload.name, "description": payload.description},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if payload.request_id:
            existing = await self.portfolios.project_by_request(student_id, payload.request_id)
            if existing:
                return self._replay_project(existing, fingerprint)
        project = Project(
            student_id=student_id,
            name=payload.name,
            description=payload.description,
            create_request_id=payload.request_id,
            create_request_hash=fingerprint if payload.request_id else None,
        )
        self.portfolios.add_project(project)
        try:
            await self.session.commit()
        except IntegrityError:
            # A concurrent request may have committed the same key after our first lookup.
            await self.session.rollback()
            if payload.request_id:
                existing = await self.portfolios.project_by_request(student_id, payload.request_id)
                if existing:
                    return self._replay_project(existing, fingerprint)
            raise
        await self.session.refresh(project)
        return ProjectView.model_validate(project)

    @staticmethod
    def _replay_project(project: Project, fingerprint: str) -> ProjectView:
        if project.create_request_hash != fingerprint:
            raise AppError("同一请求编号不能用于不同项目内容", code=4091, status_code=409)
        return ProjectView.model_validate(project)

    async def create_project_version(
        self,
        *,
        project_id: UUID,
        filename: str,
        content: bytes,
        current_user: User,
        request_id: UUID | None = None,
    ) -> tuple[ProjectVersionUploadData, bool]:
        student = await self._student(current_user)
        # PostgreSQL serializes version allocation per project, including different request keys.
        project = await self.portfolios.owned_project(project_id, student.id, lock=True)
        if not project:
            raise AppError("项目不存在或无权访问", code=4043, status_code=404)
        suffix = Path(filename).suffix.lower()
        if suffix not in {
            ".zip",
            ".pdf",
            ".docx",
            ".txt",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".bmp",
        }:
            raise AppError(
                "项目支持ZIP源代码或PDF、DOCX、TXT及常见图片作品",
                code=4022,
                status_code=415,
            )
        if len(content) > settings.max_archive_bytes:
            raise AppError("项目文件不得超过30MB", code=4023, status_code=413)
        if suffix != ".zip" and len(content) > RESUME_MAX_BYTES:
            raise AppError("作品文档不得超过10MB", code=4023, status_code=413)
        content_hash = hashlib.sha256(content).hexdigest()
        if request_id:
            existing = await self.portfolios.version_by_request(project_id, request_id)
            if existing:
                if existing.content_hash != content_hash:
                    raise AppError("同一上传请求编号不能用于不同文件", code=4092, status_code=409)
                task = await self.session.get(AnalysisTask, existing.analysis_task_id)
                if not task:
                    raise AppError(
                        "原上传任务已不存在，请创建新的上传请求", code=4093, status_code=409
                    )
                return ProjectVersionUploadData(
                    project_id=project_id,
                    version_id=existing.id,
                    task_id=task.id,
                    status=task.status,
                ), False
        version_number = await self.portfolios.next_project_version(project.id)
        version = ProjectVersion(
            project_id=project.id,
            version_number=version_number,
            archive_storage_key="",
            content_hash=content_hash,
            analysis_status="pending",
            original_filename=Path(filename.replace("\\", "/")).name[:255],
            size_bytes=len(content),
            upload_request_id=request_id,
        )
        self.portfolios.add_project_version(version)
        await self.session.flush()
        object_key = f"projects/{project.id}/versions/{version.id}{suffix}"
        self.storage.save(object_key, content)
        version.archive_storage_key = object_key
        task = AnalysisTask(
            created_by=current_user.id,
            task_type="project_scan",
            status=TaskStatus.PENDING,
            current_step="等待扫描",
        )
        self.analysis.add_task(task)
        await self.session.flush()
        version.analysis_task_id = task.id
        await self.session.commit()
        return ProjectVersionUploadData(
            project_id=project.id,
            version_id=version.id,
            task_id=task.id,
            status=task.status,
        ), True

    async def _student(self, current_user: User):
        if current_user.role not in {UserRole.STUDENT, UserRole.ADMIN}:
            raise AppError("只有学生用户可以管理简历和项目", code=4037, status_code=403)
        student = await self.portfolios.student_by_user(current_user.id)
        if not student:
            raise AppError("学生资料不存在", code=4044, status_code=404)
        return student


async def execute_resume_parse_task(task_id: UUID, version_id: UUID) -> None:
    async with async_session_factory() as session:
        token = await claim_task(session, task_id, step="解析简历文档")
        if token is None:
            return
        heartbeat = asyncio.create_task(heartbeat_task(task_id, token, async_session_factory))
        try:
            version = await session.get(ResumeVersion, version_id)
            if not version or version.analysis_task_id != task_id:
                raise AppError("简历版本已不存在", code=4045)
            storage = LocalStorage(settings.storage_base_dir)
            parsed = await run_isolated(
                process_document,
                storage.resolve(version.storage_key),
                version.mime_type,
                settings.max_document_characters,
            )
            if not await finish_task(session, task_id, token, step="简历解析完成"):
                await session.rollback()
                return
            old_section_ids = list(
                await session.scalars(
                    select(ResumeSection.id).where(ResumeSection.resume_version_id == version.id)
                )
            )
            await delete_source_chunks(session, "resume_section", old_section_ids)
            await session.execute(
                delete(ResumeSection).where(ResumeSection.resume_version_id == version.id)
            )
            sections = [
                ResumeSection(
                    resume_version_id=version.id,
                    section_type=item.section_type,
                    content=item.content,
                    page_number=item.page_number,
                )
                for item in parsed
            ]
            session.add_all(sections)
            await session.flush()
            await index_sources(
                session,
                [
                    ChunkSource(
                        source_type="resume_section",
                        source_id=section.id,
                        content=section.content,
                        metadata={
                            "resumeVersionId": str(version.id),
                            "sectionType": section.section_type,
                            "pageNumber": section.page_number,
                        },
                    )
                    for section in sections
                ],
            )
            version.parse_status = "completed"
            await session.commit()
        except Exception as exc:
            await session.rollback()
            if await finish_task(
                session,
                task_id,
                token,
                status=TaskStatus.FAILED,
                step="简历解析失败",
                error_message=exc.message
                if isinstance(exc, AppError)
                else "简历解析失败，请检查文件后重试",
            ):
                version = await session.get(ResumeVersion, version_id)
                if version:
                    version.parse_status = "failed"
                await session.commit()
            else:
                await session.rollback()
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat


async def execute_project_scan_task(task_id: UUID, version_id: UUID) -> None:
    async with async_session_factory() as session:
        token = await claim_task(session, task_id, step="解析项目文件")
        if token is None:
            return
        heartbeat = asyncio.create_task(heartbeat_task(task_id, token, async_session_factory))
        try:
            version = await session.get(ProjectVersion, version_id)
            if not version or version.analysis_task_id != task_id:
                raise AppError("项目版本已不存在", code=4043)
            storage = LocalStorage(settings.storage_base_dir)
            archive_path = storage.resolve(version.archive_storage_key)
            destination = storage.resolve(f"projects/extracted/{version.id}/{token}")
            records = await run_isolated(
                process_project,
                archive_path,
                destination,
                storage.base_dir,
                version.original_filename or "document",
                ArchiveLimits(
                    settings.max_archive_bytes,
                    settings.max_extracted_bytes,
                    settings.max_file_bytes,
                    settings.max_archive_files,
                ),
                settings.max_document_characters,
            )
            if not await finish_task(session, task_id, token, step="项目解析完成"):
                await session.rollback()
                return
            old_file_ids = list(
                await session.scalars(
                    select(ProjectFile.id).where(ProjectFile.project_version_id == version.id)
                )
            )
            await delete_source_chunks(session, "project_file", old_file_ids)
            await session.execute(
                delete(ProjectFile).where(ProjectFile.project_version_id == version.id)
            )
            files = [ProjectFile(project_version_id=version.id, **record) for record in records]
            session.add_all(files)
            await session.flush()
            contents = await asyncio.gather(
                *[
                    asyncio.to_thread(
                        storage.resolve(file.storage_key).read_text,
                        encoding="utf-8",
                        errors="replace",
                    )
                    for file in files
                ]
            )
            await index_sources(
                session,
                [
                    ChunkSource(
                        source_type="project_file",
                        source_id=file.id,
                        content=content,
                        metadata={
                            "projectVersionId": str(version.id),
                            "path": file.relative_path,
                            "contentHash": file.content_hash,
                            "language": file.language,
                        },
                    )
                    for file, content in zip(files, contents, strict=True)
                ],
            )
            version.analysis_status = "completed"
            await session.commit()
        except Exception as exc:
            await session.rollback()
            if await finish_task(
                session,
                task_id,
                token,
                status=TaskStatus.FAILED,
                step="项目解析失败",
                error_message=exc.message
                if isinstance(exc, AppError)
                else "项目解析失败，请检查文件后重试",
            ):
                version = await session.get(ProjectVersion, version_id)
                if version:
                    version.analysis_status = "failed"
                await session.commit()
            else:
                await session.rollback()
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat


async def retry_material_task(session: AsyncSession, task_id: UUID, current_user: User):
    """Return (accepted, function, args); caller schedules after this commits."""
    task = await session.get(AnalysisTask, task_id)
    if not task or task.created_by != current_user.id:
        raise AppError("分析任务不存在或无权访问", code=4041, status_code=404)
    service = PortfolioService(session)
    student = await service._student(current_user)
    if task.task_type == "resume_parse":
        version = await session.scalar(
            select(ResumeVersion)
            .join(Resume)
            .where(ResumeVersion.analysis_task_id == task.id, Resume.student_id == student.id)
        )
        function = execute_resume_parse_task
        key = version.storage_key if version else None
    elif task.task_type == "project_scan":
        version = await session.scalar(
            select(ProjectVersion)
            .join(Project)
            .where(ProjectVersion.analysis_task_id == task.id, Project.student_id == student.id)
        )
        function = execute_project_scan_task
        key = version.archive_storage_key if version else None
    else:
        raise AppError("此任务不属于材料解析任务", code=4095, status_code=409)
    if not version or not key or not service.storage.resolve(key).is_file():
        raise AppError("源文件不可用，请重新上传材料", code=4046, status_code=404)
    task = await reset_failed_task(session, task_id, current_user)
    if isinstance(version, ResumeVersion):
        version.parse_status = "pending"
    else:
        version.analysis_status = "pending"
    await session.commit()
    return TaskAccepted(task_id=task_id, status=task.status), function, (task_id, version.id)
