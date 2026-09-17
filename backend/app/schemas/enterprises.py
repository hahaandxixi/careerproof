from uuid import UUID

from pydantic import Field

from app.models.enums import MembershipRole
from app.schemas.common import APIModel


class EnterpriseCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class EnterpriseView(APIModel):
    id: UUID
    name: str
    description: str
    is_verified: bool
    role: MembershipRole
