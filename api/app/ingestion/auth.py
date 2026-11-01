"""Credential validation independent from the administrative JWT endpoints."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.projects.keys import hash_key, is_key_valid
from app.projects.services import get_project
from app.projects.tables import api_key
from utils import decrypt


async def authenticate_key(session: AsyncSession, secret: str) -> tuple[dict, dict]:
    """Validate under the project lock shared with revocation and rotation."""
    denied = HTTPException(
        401, "Invalid or expired ingestion key", headers={"WWW-Authenticate": "Bearer"}
    )
    if not secret.startswith("pgw_") or not 40 <= len(secret) <= 100:
        raise denied
    lookup = select(api_key).where(api_key.c.key_hash == hash_key(secret))
    initial = (await session.execute(lookup)).mappings().first()
    if initial is None:
        raise denied
    settings = await get_project(session, initial["project_id"], lock=True)
    key = (await session.execute(lookup)).mappings().first()
    now = datetime.now(timezone.utc)
    if not settings["enabled"] or key is None or not is_key_valid(key, now):
        raise denied
    return settings, dict(key)


async def get_replacement_key(
    session: AsyncSession, settings: dict, authenticated: dict
) -> str | None:
    """Allow a still-valid retiring key to recover from lost handoff responses."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(api_key)
        .where(api_key.c.id == authenticated["id"])
        .values(last_used_at=now)
    )
    current = (
        (
            await session.execute(
                select(api_key).where(
                    api_key.c.project_id == settings["id"],
                    api_key.c.retire_at.is_(None),
                    api_key.c.revoked_at.is_(None),
                )
            )
        )
        .mappings()
        .first()
    )
    if (
        current is not None
        and current["id"] != authenticated["id"]
        and current["encrypted_secret"]
        and is_key_valid(current, now)
    ):
        return decrypt(current["encrypted_secret"])
    return None
