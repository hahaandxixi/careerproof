"""Read only the submitted report snapshot; never impersonate its student owner."""

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.provider import redact_external_text
from app.core.config import settings
from app.core.exceptions import AppError
from app.models.analysis import MatchReport
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.models.identity import StudentProfile, User
from app.models.portfolio import Resume, ResumeVersion
from app.models.recruitment import Application, ApplicationEvent, Job
from app.schemas.applications import ApplicationCreate, ApplicationReply
from app.services.analysis import AnalysisService
from app.services.jobs import JobService
from app.services.notifications import notify_application_event
from app.tools.storage import LocalStorage

CONSENT_VERSION = "application-report-v1"


def _reply_has_citation(text: str, citation_id: str) -> bool:
    # A saved R1-E1 link must not survive when the text only says R1-E10.
    return bool(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(citation_id)}(?![A-Za-z0-9_-])", text))


_REPLY_MARKER = re.compile(r"(?m)^(【第[1-9]\d*项：[^\r\n]+】)[ \t]*\r?$")


def _read_resume_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _reply_blocks(text: str, marker: str) -> list[str]:
    markers = list(_REPLY_MARKER.finditer(text))
    return [
        text[match.end() : markers[index + 1].start() if index + 1 < len(markers) else len(text)]
        for index, match in enumerate(markers)
        if match.group(1) == marker
    ]


def _reply_references(snapshot: dict, text: str, references: list[dict]) -> list[dict]:
    """Accept only links named in the human reply and its frozen requirement."""
    if not isinstance(references, list):
        raise ValueError("Invalid reply references")
    rows = snapshot.get("items", [])
    items = {
        str(row.get("requirementId")): (index, row)
        for index, row in enumerate(rows)
        if isinstance(row, dict) and row.get("requirementId")
    }
    safe = []
    seen = set()
    for reference in references:
        if not isinstance(reference, dict):
            raise ValueError("Invalid reply reference")
        requirement_id = str(reference.get("requirementId", ""))
        indexed_row = items.get(requirement_id)
        if not indexed_row or requirement_id in seen:
            raise ValueError("Reply requirement is outside the frozen report")
        seen.add(requirement_id)
        index, row = indexed_row
        title = row.get("requirementTitle") or row.get("skill") or "岗位要求"
        marker = f"【第{index + 1}项：{title}】"
        blocks = _reply_blocks(text, marker)
        legacy_unique = (
            f"【{title}】" in text
            and sum(
                (other.get("requirementTitle") or other.get("skill") or "岗位要求") == title
                for other in rows
                if isinstance(other, dict)
            ) == 1
        )
        if not blocks and not legacy_unique:
            raise ValueError("Reply no longer contains the linked requirement")
        citation_ids = reference.get("citationIds", [])
        if not isinstance(citation_ids, list) or len(citation_ids) > 6:
            raise ValueError("Invalid reply citations")
        evidence = row.get("evidenceList") or ([row["evidence"]] if row.get("evidence") else [])
        allowed = {
            entry.get("citationId") for entry in evidence if isinstance(entry, dict)
        }
        if (
            len(citation_ids) != len(set(citation_ids))
            or any(
                not isinstance(cid, str)
                or cid not in allowed
                or not any(_reply_has_citation(block, cid) for block in blocks or [text])
                for cid in citation_ids
            )
        ):
            raise ValueError("Reply citation is outside its frozen requirement")
        safe.append({"requirementId": requirement_id, "citationIds": citation_ids})
    return safe


def _read_reply_references(item: Application) -> list[dict]:
    try:
        return _reply_references(
            item.report_snapshot or {}, item.reply_text or "", item.reply_references or []
        )
    except (KeyError, TypeError, ValueError):
        return []


def reply_context_for_requirement(item: Application, requirement_id: UUID) -> dict | None:
    """Extract only the student's own linked human-reply block from a frozen application."""
    reference = next(
        (
            value
            for value in _read_reply_references(item)
            if value["requirementId"] == str(requirement_id)
        ),
        None,
    )
    if reference is None:
        return None
    rows = item.report_snapshot.get("items", [])
    indexed = next(
        (
            (index, row)
            for index, row in enumerate(rows)
            if isinstance(row, dict) and row.get("requirementId") == str(requirement_id)
        ),
        None,
    )
    if indexed is None:
        return None
    index, row = indexed
    title = row.get("requirementTitle") or row.get("skill") or "岗位要求"
    blocks = _reply_blocks(item.reply_text or "", f"【第{index + 1}项：{title}】")
    excerpt = "\n\n".join(block.strip() for block in blocks if block.strip())
    if not excerpt:
        return None
    return {
        "applicationId": str(item.id),
        "reportId": str(item.report_id),
        "requirementId": str(requirement_id),
        "replyKind": item.reply_kind,
        "text": excerpt,
        "citationIds": reference["citationIds"],
    }


class ApplicationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _student(self, user):
        if user.role != UserRole.STUDENT:
            raise AppError("请使用学生账号", status_code=403, code=4037)
        student = await self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user.id)
        )
        if not student:
            raise AppError("学生资料不存在", status_code=404, code=4044)
        return student

    async def _access(self, application_id, user, *, enterprise=False, lock=False):
        query = select(Application).where(Application.id == application_id)
        if lock:
            # A locked read must observe the row as of the lock, not a copy left in this
            # session's identity map by an earlier transaction (e.g. a download recheck).
            query = query.with_for_update().execution_options(populate_existing=True)
        item = await self.session.scalar(query)
        if not item or not item.consent_at or not item.report_snapshot:
            raise AppError("投递不存在或无权访问", status_code=404, code=4049)
        job = await self.session.get(Job, item.job_id)
        if enterprise:
            if (
                user.role != UserRole.ENTERPRISE
                or item.status == "withdrawn"
                or not await JobService(self.session).can_manage(job, user)
            ):
                raise AppError("投递不存在或无权访问", status_code=404, code=4049)
        else:
            student = await self._student(user)
            if item.student_id != student.id:
                raise AppError("投递不存在或无权访问", status_code=404, code=4049)
        return item, job

    async def _event(self, item, user, event_type, detail):
        existing = await self.session.scalar(
            select(ApplicationEvent.id).where(
                ApplicationEvent.application_id == item.id,
                ApplicationEvent.event_type == event_type,
            )
        )
        if existing:
            return
        event = ApplicationEvent(
            application_id=item.id, actor_id=user.id, event_type=event_type, detail=detail
        )
        self.session.add(event)
        await self.session.flush()
        await notify_application_event(self.session, item, event)
        self.session.add(
            AuditLog(
                actor_id=user.id,
                action=f"application.{event_type}",
                resource_type="application",
                resource_id=str(item.id),
                details={"reportId": str(item.report_id)},
            )
        )
        item.version += 1

    async def create(self, request: ApplicationCreate, user):
        student = await self._student(user)
        # This checks task ownership through the existing student report access path.
        report_view = await AnalysisService(self.session).get_report(request.report_id, user)
        report = await self.session.get(MatchReport, request.report_id)
        # Serialize submissions and job closure against the same job row lock.
        job = await self.session.scalar(
            select(Job).where(Job.id == report.job_id).with_for_update()
        )
        if job.status != "published":
            raise AppError("岗位已关闭，不能投递", status_code=409, code=4098)
        existing = await self.session.scalar(
            select(Application).where(
                Application.job_id == job.id, Application.student_id == student.id
            )
        )
        if existing:
            if existing.report_id == report.id and existing.status != "withdrawn":
                return await self.view(existing, job)
            raise AppError("该岗位已有投递；本期不覆盖已授权的材料版本", status_code=409, code=4098)
        # Lock the student's row so concurrent submissions to distinct jobs share one limit.
        await self.session.scalar(
            select(StudentProfile).where(StudentProfile.id == student.id).with_for_update()
        )
        count = await self.session.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.student_id == student.id,
                Application.created_at >= datetime.now(UTC) - timedelta(days=1),
            )
        )
        if count >= 20:
            raise AppError("24小时内最多投递20个岗位，请稍后再试", status_code=429, code=4298)
        snapshot = report_view.model_dump(mode="json", by_alias=True)
        item = Application(
            job_id=job.id,
            student_id=student.id,
            report_id=report.id,
            report_snapshot=snapshot,
            status="submitted",
            consent_at=datetime.now(UTC),
            consent_version=CONSENT_VERSION,
        )
        self.session.add(item)
        try:
            await self.session.flush()
            await self._event(
                item,
                user,
                "submitted",
                "学生明确授权该岗位企业查看本次固定报告、引用片段并获取本次简历文件",
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("投递已存在，请刷新查看", status_code=409, code=4098) from exc
        return await self.view(item, job)

    async def view(self, item, job, include_report=False):
        student = await self.session.get(StudentProfile, item.student_id)
        user = await self.session.get(User, student.user_id)
        events = await self.session.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == item.id)
            .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
        )
        result = {
            "id": str(item.id),
            "jobId": str(job.id),
            "jobTitle": job.title,
            "companyName": job.company_name,
            "candidateName": user.display_name,
            "reportId": str(item.report_id),
            "status": item.status,
            "createdAt": item.created_at.isoformat(),
            "consentVersion": item.consent_version,
            "replyKind": item.reply_kind,
            "replyText": item.reply_text,
            "replyReferences": _read_reply_references(item),
            "overallScore": item.report_snapshot.get("overallScore"),
            "events": [
                {"type": e.event_type, "at": e.created_at.isoformat(), "detail": e.detail}
                for e in events
            ],
        }
        result["dimensions"] = [
            {
                "requirementId": i["requirementId"],
                "title": i.get("requirementTitle") or i.get("skill") or "岗位要求",
                "skill": i.get("skill", ""),
                "score": i.get("finalScore"),
                "verdict": i.get("verdict"),
                "weight": i.get("weight", 1),
                "evidenceLevel": i.get("evidenceLevel"),
                "evidenceLevelSource": i.get("evidenceLevelSource"),
                "evidenceLevelVersion": i.get("evidenceLevelVersion"),
                "formulaVersion": i.get("formulaVersion"),
            }
            for i in item.report_snapshot.get("items", [])
        ]
        # Equal requirement IDs can have edited text/weight or a different scoring version.
        basis = {
            "context": item.report_snapshot.get("evidenceContextVersion"),
            "criteria": sorted(
                [
                    {
                        k: d.get(k)
                        for k in (
                            "requirementId",
                            "title",
                            "skill",
                            "weight",
                            "evidenceLevelVersion",
                            "formulaVersion",
                        )
                    }
                    for d in result["dimensions"]
                ],
                key=lambda d: d["requirementId"],
            ),
        }
        result["comparisonBasis"] = hashlib.sha256(
            json.dumps(basis, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        if include_report:
            result["report"] = item.report_snapshot
        return result

    async def mine(self, user):
        student = await self._student(user)
        items = await self.session.scalars(
            select(Application)
            .where(Application.student_id == student.id, Application.consent_at.is_not(None))
            .order_by(Application.created_at.desc())
            .limit(100)
        )
        return [await self.view(item, await self.session.get(Job, item.job_id)) for item in items]

    async def candidates(self, job_id, user):
        job = await self.session.get(Job, job_id)
        if (
            not job
            or user.role != UserRole.ENTERPRISE
            or not await JobService(self.session).can_manage(job, user)
        ):
            raise AppError("岗位不存在或无管理权限", status_code=404, code=4040)
        items = await self.session.scalars(
            select(Application)
            .where(
                Application.job_id == job.id,
                Application.consent_at.is_not(None),
                Application.status != "withdrawn",
            )
            .order_by(Application.created_at.desc())
            .limit(100)
        )
        # The report is not exported in list responses: opening it is an explicit audited action.
        return [await self.view(item, job) for item in items]

    async def detail(self, application_id, user):
        # A notification may reference an application older than the recent list.
        item, job = await self._access(
            application_id, user, enterprise=user.role == UserRole.ENTERPRISE
        )
        return await self.view(item, job)

    async def open(self, application_id, user):
        item, job = await self._access(application_id, user, enterprise=True, lock=True)
        await self._event(item, user, "viewed", "企业请求查看已授权报告；不代表进入面试或录用")
        if item.status == "submitted":
            item.status = "viewed"
        await self.session.commit()
        return await self.view(item, job, include_report=True)

    async def reply(self, application_id, request: ApplicationReply, user):
        item, job = await self._access(application_id, user, enterprise=True, lock=True)
        if item.status not in {"viewed", "downloaded"}:
            raise AppError("请先查看报告；已发送的回复本期不可覆盖", status_code=409, code=4098)
        reply_text = redact_external_text(request.text)
        try:
            references = _reply_references(
                item.report_snapshot,
                reply_text,
                [
                    reference.model_dump(mode="json", by_alias=True)
                    for reference in request.references
                ],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(
                "回复引用必须对应本次投递固定报告中的要求与片段",
                status_code=422,
                code=4224,
            ) from exc
        item.reply_kind, item.reply_text, item.reply_references = (
            request.kind, reply_text, references
        )
        item.status = "replied"
        await self._event(item, user, "replied", f"企业已回复：{request.kind}；以回复正文为准")
        await self.session.commit()
        return await self.view(item, job)

    async def withdraw(self, application_id, user):
        item, job = await self._access(application_id, user, lock=True)
        if item.status != "withdrawn":
            item.status = "withdrawn"
            await self._event(
                item, user, "withdrawn", "学生撤回授权；企业后续访问被拒绝，已下载副本无法追回"
            )
            await self.session.commit()
        return await self.view(item, job)

    async def _resume_version(self, item: Application) -> ResumeVersion:
        material = next(
            (m for m in item.report_snapshot.get("materials", []) if m.get("kind") == "resume"),
            None,
        )
        if not material:
            raise AppError("本次报告没有简历文件", status_code=404, code=4045)
        version = await self.session.scalar(
            select(ResumeVersion)
            .join(Resume)
            .where(ResumeVersion.id == UUID(material["id"]), Resume.student_id == item.student_id)
        )
        if not version or version.content_hash != material.get("contentHash"):
            raise AppError("简历版本校验失败", status_code=409, code=4096)
        return version

    async def download(self, application_id, user):
        # Phase 1 holds the row lock only for authorization and version validation; it
        # must not span the file read, or a slow disk keeps a student withdraw waiting.
        item, _job = await self._access(application_id, user, enterprise=True, lock=True)
        if item.status == "submitted":
            raise AppError("请先查看报告再下载简历", status_code=409, code=4098)
        version = await self._resume_version(item)
        storage_key, expected_hash = version.storage_key, version.content_hash
        mime, filename = version.mime_type, version.original_filename or "resume.txt"
        # Nothing is written yet; committing releases the row lock before any file I/O.
        await self.session.commit()
        # Phase 2 reads in a worker thread: neither the event loop nor any row lock waits.
        try:
            storage = LocalStorage(settings.storage_base_dir).resolve(storage_key)
            content = await asyncio.to_thread(_read_resume_bytes, storage)
        except (OSError, ValueError) as exc:
            raise AppError("简历文件暂不可用", status_code=404, code=4046) from exc
        # Phase 3 re-locks: a withdrawal during the read must deny the file and leave no
        # downloaded event, no status change and no version bump behind.
        item, _job = await self._access(application_id, user, enterprise=True, lock=True)
        version = await self._resume_version(item)
        if (version.storage_key, version.content_hash) != (storage_key, expected_hash):
            raise AppError("简历版本校验失败", status_code=409, code=4096)
        if hashlib.sha256(content).hexdigest() != version.content_hash:
            raise AppError("简历文件内容校验失败", status_code=409, code=4096)
        await self._event(
            item, user, "downloaded", "平台已向企业交付授权简历下载响应；不证明对方保存、阅读或录用"
        )
        if item.status == "viewed":
            item.status = "downloaded"
        await self.session.commit()
        return content, mime, filename
