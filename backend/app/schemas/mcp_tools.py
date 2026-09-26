"""Explicit read-only report export grants for local MCP clients."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExportGrant(StrictInput):
    report_ids: list[UUID] = Field(min_length=1, max_length=20)
    external_client_consent: bool = False


class ToolInvocation(StrictInput):
    tool: str = Field(min_length=1, max_length=60)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ReportQuery(StrictInput):
    report_id: UUID


class EvidenceQuery(ReportQuery):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=5)


class ComparisonQuery(StrictInput):
    base_id: UUID
    target_id: UUID
