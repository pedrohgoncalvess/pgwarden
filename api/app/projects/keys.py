"""Generate, hash, validate, and rotate project-scoped ingestion credentials."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.projects.tables import api_key, project
from utils import encrypt


def hash_key(secret: str) -> str:
    """Hash a high-entropy credential for indexed lookup."""
    return hashlib.sha256(secret.encode()).hexdigest()


def is_key_valid(key: dict, now: datetime) -> bool:
    """Reject revoked, expired, or fully retired credentials."""
    return key["revoked_at"] is None and all(
        key[field] is None or now < key[field] for field in ("expires_at", "retire_at")
    )


async def issue_key(session: AsyncSession, settings: dict, grace_hours: int) -> dict:
    """Replace a project's current key under the caller's project row lock."""
    now = datetime.now(timezone.utc)
    retire_at = now + timedelta(hours=grace_hours)
    # An immediate rotation is also the recovery path for a compromised key.
    if grace_hours == 0:
        await session.execute(
            update(api_key)
            .where(
                api_key.c.project_id == settings["id"],
                api_key.c.revoked_at.is_(None),
            )
            .values(revoked_at=now, encrypted_secret=None)
        )
    else:
        await session.execute(
            update(api_key)
            .where(
                api_key.c.project_id == settings["id"],
                api_key.c.retire_at.is_(None),
                api_key.c.revoked_at.is_(None),
            )
            .values(retire_at=retire_at, encrypted_secret=None)
        )
    secret = "pgw_" + secrets.token_urlsafe(32)
    lifetime = settings["key_expiration_days"]
    values = {
        "id": uuid4(),
        "project_id": settings["id"],
        "key_hash": hash_key(secret),
        "prefix": secret[:12],
        "created_at": now,
        "expires_at": now + timedelta(days=lifetime) if lifetime else None,
        "retire_at": None,
        "revoked_at": None,
        "last_used_at": None,
        # Automatic handoff needs the successor to survive a lost HTTP response.
        "encrypted_secret": encrypt(secret) if grace_hours else None,
    }
    await session.execute(api_key.insert().values(**values))
    interval = settings["rotation_interval_days"]
    await session.execute(
        update(project)
        .where(project.c.id == settings["id"])
        .values(
            next_rotation_at=now + timedelta(days=interval) if interval else None,
        )
    )
    return {"key": secret, "metadata": values}
