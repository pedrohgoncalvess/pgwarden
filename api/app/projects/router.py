"""Administrator-only project and key management routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from app.auth.services import get_current_user
from app.projects import services
from app.projects.models import (
    IssuedKey,
    KeyView,
    ProjectCreated,
    ProjectSettings,
    ProjectView,
    RotationRequest,
)
from app.projects.tables import api_key, project
from database.connection import DatabaseConnection
from database.models.base import User


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Keep ingestion provisioning separate from ordinary user access."""
    if not user.is_admin:
        raise HTTPException(403, "Administrator access required")
    return user


router = APIRouter(
    prefix="/projects", tags=["projects"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[ProjectView])
async def list_projects(response: Response) -> list[dict]:
    """List project policies and ingestion activity."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return list(
            (
                await session.execute(select(project).order_by(project.c.created_at))
            ).mappings()
        )


@router.post("", response_model=ProjectCreated, status_code=201, dependencies=[Depends(require_admin)])
async def create_project(settings: ProjectSettings, response: Response) -> dict:
    """Create a project and reveal its initial credential once."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return await services.create_project(session, settings)


@router.put("/{project_id}", response_model=ProjectView, dependencies=[Depends(require_admin)])
async def update_project(
    project_id: UUID, settings: ProjectSettings, response: Response
) -> dict:
    """Change project availability or future key policies."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return await services.update_project(session, project_id, settings)


@router.get("/{project_id}/keys", response_model=list[KeyView], dependencies=[Depends(require_admin)])
async def list_keys(project_id: UUID, response: Response) -> list[dict]:
    """Return key prefixes and lifecycle dates without secret material."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        await services.get_project(session, project_id)
        return list(
            (
                await session.execute(
                    select(api_key)
                    .where(
                        api_key.c.project_id == project_id,
                    )
                    .order_by(api_key.c.created_at.desc())
                )
            ).mappings()
        )


@router.post("/{project_id}/keys/rotate", response_model=IssuedKey, dependencies=[Depends(require_admin)])
async def rotate_key(
    project_id: UUID, body: RotationRequest, response: Response
) -> dict:
    """Rotate manually, optionally keeping old credentials briefly valid."""
    response.headers["Cache-Control"] = "no-store"
    async with DatabaseConnection() as session:
        return await services.rotate_key(session, project_id, body.grace_hours)


@router.delete("/{project_id}/keys/{key_id}", status_code=204, dependencies=[Depends(require_admin)])
async def revoke_key(project_id: UUID, key_id: UUID) -> Response:
    """Revoke one key immediately."""
    async with DatabaseConnection() as session:
        await services.revoke_key(session, project_id, key_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
