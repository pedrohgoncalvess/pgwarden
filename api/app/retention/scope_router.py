"""Administrator routes for scoped policy inheritance."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from app.projects.router import require_admin
from app.retention import scopes
from app.retention.models import RetentionWindow
from app.retention.scoped_preview import preview_scope
from database.connection import DatabaseConnection


router = APIRouter(prefix="/retention/scopes", tags=["retention"],
                   dependencies=[Depends(require_admin)])
Scope = Literal["global", "project", "server"]


@router.get("")
async def list_settings(response: Response) -> dict[str, Any]:
    """Return overrides and their effective inheritance."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return await scopes.list_settings(session)


@router.put("/{scope}/{scope_id}/{name}")
async def save_scope(
    scope: Scope, scope_id: UUID, name: str, window: RetentionWindow,
    response: Response,
) -> dict[str, Any]:
    """Save a policy; '*' means every table without a more specific rule."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        await scopes.save_policy(session, scope, scope_id, name, window)
        await session.commit()
        return await scopes.list_settings(session)


@router.delete("/{scope}/{scope_id}/{name}", status_code=204)
async def inherit_scope(scope: Scope, scope_id: UUID, name: str) -> Response:
    """Remove a project/server override and restore inheritance."""
    async with DatabaseConnection() as session:
        await scopes.remove_policy(session, scope, scope_id, name)
        await session.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/{scope}/{scope_id}/{name}/preview")
async def preview_scoped(
    scope: Scope, scope_id: UUID, name: str, window: RetentionWindow,
    response: Response,
) -> dict[str, Any]:
    """Estimate only data affected by the proposed inheritance change."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        await session.execute(text("SET LOCAL statement_timeout='30s'"))
        return await preview_scope(session, scope, scope_id, name, window)
