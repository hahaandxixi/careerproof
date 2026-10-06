from typing import Annotated
from uuid import UUID

from pydantic import ConfigDict, Field, StrictInt, StrictStr, StringConstraints

from app.schemas.common import APIModel

DraftText = Annotated[StrictStr, StringConstraints(strip_whitespace=False, max_length=6000)]
CitationId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class AnswerDraftReference(APIModel):
    model_config = ConfigDict(extra="forbid")

    report_id: UUID
    requirement_id: UUID
    citation_id: CitationId


class AnswerDraftSave(APIModel):
    """Full replacement of the private draft; expectedRevision guards concurrency."""

    model_config = ConfigDict(extra="forbid")

    text: DraftText
    references: list[AnswerDraftReference] = Field(max_length=20)
    expected_revision: Annotated[StrictInt, Field(ge=0)]
