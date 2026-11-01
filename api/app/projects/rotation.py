"""Periodic automatic rotation, coordinated across API workers by row locks."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.projects.keys import issue_key
from app.projects.tables import api_key, project
from database.connection import DatabaseConnection


async def rotate_due_keys(session: AsyncSession) -> int:
    """Rotate due projects once, skipping projects another worker has locked."""
    now = datetime.now(timezone.utc)
    rows = (
        (
            await session.execute(
                select(project)
                .where(
                    project.c.enabled.is_(True),
                    project.c.rotation_interval_days.is_not(None),
                    project.c.next_rotation_at <= now,
                )
                .with_for_update(skip_locked=True)
                .limit(100)
            )
        )
        .mappings()
        .all()
    )
    rotated = 0
    for settings in rows:
        current = (
            await session.execute(
                select(api_key.c.id).where(
                    api_key.c.project_id == settings["id"],
                    api_key.c.retire_at.is_(None),
                    api_key.c.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if current is not None:
            await issue_key(session, dict(settings), settings["rotation_grace_hours"])
            rotated += 1
        else:
            await session.execute(
                update(project)
                .where(project.c.id == settings["id"])
                .values(next_rotation_at=None)
            )
    previous = api_key.alias("previous_key")
    needs_handoff = (
        select(previous.c.id)
        .where(
            previous.c.project_id == api_key.c.project_id,
            previous.c.revoked_at.is_(None),
            previous.c.retire_at > now,
            or_(previous.c.expires_at.is_(None), previous.c.expires_at > now),
        )
        .exists()
    )
    await session.execute(
        update(api_key)
        .where(
            api_key.c.encrypted_secret.is_not(None),
            ~needs_handoff,
        )
        .values(encrypted_secret=None)
    )
    await session.commit()
    return rotated


async def run_rotation_worker() -> None:
    """Apply persisted rotation schedules approximately once per minute."""
    while True:
        try:
            async with DatabaseConnection() as session:
                await rotate_due_keys(session)
        except Exception as error:
            logging.getLogger(__name__).warning(
                "Ingestion key rotation failed (%s)", type(error).__name__
            )
        await asyncio.sleep(60)
