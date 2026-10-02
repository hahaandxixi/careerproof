"""Generic event notices; authorization is checked again before navigation."""

from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.core.exceptions import AppError
from app.models.enums import MembershipRole, UserRole
from app.models.identity import EnterpriseMembership, StudentProfile, User
from app.models.notification import Notification
from app.models.recruitment import Application, ApplicationEvent, Job
from app.services.jobs import JobService

MESSAGES = {
    "submitted": "投递已提交",
    "viewed": "企业已请求查看报告；不代表进入面试或录用",
    "downloaded": "平台已交付简历下载响应；不证明对方保存或阅读",
    "replied": "企业已回复，请在投递详情核对正文",
    "withdrawn": "投递授权已撤回；已下载副本无法追回",
}


async def notify_application_event(session, item, event):
    # Caller holds the application/job lock. The event and all notices commit together.
    student = await session.get(StudentProfile, item.student_id)
    recipients = {student.user_id}
    if event.event_type in {"submitted", "withdrawn"}:
        job = await session.get(Job, item.job_id)
        managers = await session.scalars(
            select(EnterpriseMembership.user_id)
            .join(User)
            .where(
                EnterpriseMembership.enterprise_id == job.enterprise_id,
                EnterpriseMembership.is_active.is_(True),
                EnterpriseMembership.role.in_([MembershipRole.OWNER, MembershipRole.HR]),
                User.is_active.is_(True),
                User.role == UserRole.ENTERPRISE,
            )
        )
        recipients.update(managers)
    session.add_all([Notification(event_id=event.id, recipient_id=uid) for uid in recipients])


class NotificationService:
    def __init__(self, session):
        self.session = session

    async def _owned(self, notification_id, user):
        row = await self.session.scalar(
            select(Notification).where(
                Notification.id == notification_id, Notification.recipient_id == user.id
            )
        )
        if row is None:
            raise AppError("通知不存在或无权访问", status_code=404, code=4049)
        return row

    async def _target(self, row, user):
        event = await self.session.get(ApplicationEvent, row.event_id)
        item = await self.session.get(Application, event.application_id)
        job = await self.session.get(Job, item.job_id)
        if not item.consent_at or not item.report_snapshot:
            return event, None
        if user.role == UserRole.STUDENT:
            student = await self.session.get(StudentProfile, item.student_id)
            if student.user_id == user.id:
                return event, f"/applications#application-{item.id}"
        elif user.role == UserRole.ENTERPRISE:
            if item.status != "withdrawn" and await JobService(self.session).can_manage(job, user):
                return event, f"/jobs/{job.id}/applications#application-{item.id}"
        return event, None

    async def count(self, user):
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
            )
            or 0
        )

    async def list(self, user, page, page_size, unread_only):
        conditions = [Notification.recipient_id == user.id]
        if unread_only:
            conditions.append(Notification.read_at.is_(None))
        total = await self.session.scalar(
            select(func.count()).select_from(Notification).where(*conditions)
        )
        page = min(page, max(1, ((total or 0) + page_size - 1) // page_size))
        rows = await self.session.scalars(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = []
        for row in rows:
            event, href = await self._target(row, user)
            # Never store or expose candidate identity, evidence or reply text in a notice.
            title = MESSAGES.get(event.event_type, "投递状态已更新")
            if user.role == UserRole.ENTERPRISE and event.event_type == "submitted":
                title = "收到一份新的授权投递"
            if href is None:
                title = "投递授权已撤回或当前已无访问权限"
            items.append(
                {
                    "id": str(row.id),
                    "type": event.event_type,
                    "title": title,
                    "createdAt": row.created_at.isoformat(),
                    "readAt": row.read_at.isoformat() if row.read_at else None,
                    "accessible": href is not None,
                }
            )
        return {
            "items": items,
            "total": int(total or 0),
            "page": page,
            "pageSize": page_size,
            "unreadCount": await self.count(user),
        }

    async def read(self, notification_id, user):
        await self._owned(notification_id, user)
        await self.session.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.recipient_id == user.id,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
        )
        await self.session.commit()
        return {"unreadCount": await self.count(user)}

    async def read_all(self, user):
        await self.session.execute(
            update(Notification)
            .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(UTC))
        )
        await self.session.commit()
        return {"unreadCount": await self.count(user)}

    async def target(self, notification_id, user):
        row = await self._owned(notification_id, user)
        _event, href = await self._target(row, user)
        if href is None:
            raise AppError("投递已撤回或当前无访问权限，请刷新通知", status_code=404, code=4049)
        return {"href": href}
