"""Transactional project administration."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.projects.keys import issue_key
from app.projects.models import ProjectSettings
from app.projects.tables import api_key, project


async def get_project(
    session: AsyncSession, project_id: UUID, lock: bool = False
) -> dict:
    """Find a project, optionally locking it for credential changes."""
    statement = select(project).where(project.c.id == project_id)
    if lock:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).mappings().first()
    if row is None:
        raise HTTPException(404, "Project not found")
    return dict(row)


async def create_project(session: AsyncSession, settings: ProjectSettings) -> dict:
    """Create a project and its first key in one transaction."""
    values = {
        **settings.model_dump(),
        "id": uuid4(),
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await session.execute(project.insert().values(**values))
        credential = await issue_key(session, values, 0)
        result = await get_project(session, values["id"])
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "A project with this name already exists") from None
    return {"project": result, "credential": credential}


async def update_project(
    session: AsyncSession, project_id: UUID, settings: ProjectSettings
) -> dict:
    """Update policies without silently changing an existing key's lifetime."""
    await get_project(session, project_id, lock=True)
    current = (
        (
            await session.execute(
                select(api_key).where(
                    api_key.c.project_id == project_id,
                    api_key.c.retire_at.is_(None),
                    api_key.c.revoked_at.is_(None),
                )
            )
        )
        .mappings()
        .first()
    )
    interval = settings.rotation_interval_days
    next_rotation = (
        current["created_at"] + timedelta(days=interval)
        if current and interval
        else None
    )
    try:
        await session.execute(
            update(project)
            .where(project.c.id == project_id)
            .values(
                **settings.model_dump(),
                next_rotation_at=next_rotation,
            )
        )
        result = await get_project(session, project_id)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "A project with this name already exists") from None
    return result


async def rotate_key(session: AsyncSession, project_id: UUID, grace_hours: int) -> dict:
    """Issue a replacement credential with an explicit overlap policy."""
    settings = await get_project(session, project_id, lock=True)
    result = await issue_key(session, settings, grace_hours)
    await session.commit()
    return result


async def revoke_key(session: AsyncSession, project_id: UUID, key_id: UUID) -> None:
    """Revoke a credential immediately without recreating it automatically."""
    await get_project(session, project_id, lock=True)
    result = await session.execute(
        update(api_key)
        .where(
            api_key.c.project_id == project_id,
            api_key.c.id == key_id,
        )
        .values(revoked_at=datetime.now(timezone.utc), encrypted_secret=None)
        .returning(api_key.c.retire_at)
    )
    revoked = result.first()
    if revoked is None:
        raise HTTPException(404, "Key not found")
    if revoked.retire_at is None:
        await session.execute(
            update(project)
            .where(project.c.id == project_id)
            .values(next_rotation_at=None)
        )
    await session.commit()
