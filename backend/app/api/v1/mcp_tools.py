"""MCP bridge endpoints: explicit scope grants, bearer-only read calls and revocation."""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import bearer, get_current_user
from app.core.database import get_session
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.models.identity import User
from app.repositories.users import UserRepository
from app.schemas.common import success
from app.schemas.mcp_tools import ExportGrant, ToolInvocation
from app.services.mcp_tools import audit, invoke_tool, issue_grant

router = APIRouter(prefix="/mcp-tools", tags=["mcp-tools"])


async def read_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
):
    try:
        if not credentials:
            raise AppError("A dedicated read-only bearer token is required", status_code=401)
        claims = decode_token(credentials.credentials, "mcp_readonly")
        user = await UserRepository(session).get(UUID(claims["sub"]))
        if (
            not user
            or not user.is_active
            or user.role != UserRole.STUDENT
            or not isinstance(claims.get("reports"), list)
            or not isinstance(claims.get("jti"), str)
        ):
            raise AppError("Read-only credentials are invalid", status_code=401)
        return user, claims
    except (AppError, ValueError, KeyError):
        await audit(session, None, "mcp.auth_denied", None, {"status": "rejected"})
        raise AppError("Read-only credentials are invalid or expired", status_code=401) from None


@router.post("/grants")
async def grant(
    request: ExportGrant,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await issue_grant(session, user, request))


@router.delete("/grants/{grant_id}")
async def revoke(
    grant_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    grant = await session.scalar(
        select(AuditLog)
        .where(
            AuditLog.actor_id == user.id,
            AuditLog.resource_id == str(grant_id),
            AuditLog.action == "mcp.grant",
        )
        .with_for_update()
    )
    if not grant:
        raise AppError("只读授权不存在或无权撤销", status_code=404)
    await audit(session, user.id, "mcp.revoke", str(grant_id), {"status": "revoked"})
    return success({"revoked": True})


@router.post("/invoke")
async def invoke(
    request: ToolInvocation,
    identity=Depends(read_identity),
    session: AsyncSession = Depends(get_session),
):
    user, claims = identity
    return success(await invoke_tool(session, user, claims, request))
