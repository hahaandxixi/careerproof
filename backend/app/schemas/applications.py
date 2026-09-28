from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class ApplicationCreate(APIModel):
    report_id: UUID
    share_consent: Literal[True]


class ApplicationReply(APIModel):
    kind: Literal["interview", "continue", "declined"]
    text: str = Field(min_length=1, max_length=2000)
