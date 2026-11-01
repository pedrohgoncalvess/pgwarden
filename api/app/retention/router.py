"""Administrator endpoints for metric retention policies."""

from typing import Any

from fastapi import APIRouter, Depends, Response

from app.projects.router import require_admin
from app.retention import services
from app.retention import global_policies
from app.retention.models import RetentionWindow
from database.connection import DatabaseConnection


router = APIRouter(
    prefix="/retention", tags=["retention"], dependencies=[Depends(require_admin)]
)


@router.get("")
async def list_policies(response: Response) -> list[dict[str, Any]]:
    """Return policies for the PGWarden metric hypertables."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return await services.list_policies(session)


@router.post("/global/preview")
async def preview_global(
    window: RetentionWindow, response: Response
) -> dict[str, Any]:
    """Preview one retention duration across all current metric hypertables."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return await global_policies.preview_global(session, window)


@router.put("/global")
async def update_global(
    window: RetentionWindow, response: Response
) -> list[dict[str, Any]]:
    """Replicate the duration to all metric tables in one transaction."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return await global_policies.update_global(session, window)


@router.post("/{name}/preview")
async def preview_policy(
    name: str, window: RetentionWindow, response: Response
) -> dict[str, Any]:
    """Simulate storage changes without modifying data or policies."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return await services.preview_policy(session, name, window)


@router.put("/{name}")
async def update_policy(
    name: str, window: RetentionWindow, response: Response
) -> dict[str, Any]:
    """Save the policy for subsequent background retention runs."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return await services.update_policy(session, name, window)
