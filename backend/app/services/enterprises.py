from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.enums import MembershipRole, UserRole
from app.models.identity import Enterprise, EnterpriseMembership, User
from app.schemas.enterprises import EnterpriseCreate, EnterpriseView


class EnterpriseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def mine(self, user: User) -> list[EnterpriseView]:
        rows = await self.session.execute(
            select(Enterprise, EnterpriseMembership.role)
            .join(EnterpriseMembership, EnterpriseMembership.enterprise_id == Enterprise.id)
            .where(
                EnterpriseMembership.user_id == user.id,
                EnterpriseMembership.is_active.is_(True),
            )
            .order_by(Enterprise.created_at)
        )
        return [self._view(enterprise, role) for enterprise, role in rows]

    async def create(self, request: EnterpriseCreate, user: User) -> EnterpriseView:
        if user.role not in {UserRole.ENTERPRISE, UserRole.ADMIN}:
            raise AppError("只有企业账号可以创建组织", code=4033, status_code=403)
        enterprise = Enterprise(name=request.name, description=request.description)
        self.session.add(enterprise)
        await self.session.flush()
        self.session.add(
            EnterpriseMembership(
                enterprise_id=enterprise.id,
                user_id=user.id,
                role=MembershipRole.OWNER,
                is_active=True,
            )
        )
        await self.session.commit()
        return self._view(enterprise, MembershipRole.OWNER)

    @staticmethod
    def _view(enterprise: Enterprise, role: MembershipRole) -> EnterpriseView:
        return EnterpriseView(
            id=enterprise.id,
            name=enterprise.name,
            description=enterprise.description,
            is_verified=enterprise.is_verified,
            role=role,
        )
