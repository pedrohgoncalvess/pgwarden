"""Recheck grants before delivering each event from a long-lived connection."""
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from app.access.policy import access_context, allows
from app.access.services import load_access
from database.connection import DatabaseConnection
from database.models.base.user import User


async def protect_stream(
    source: AsyncIterator[Any], kind: str, public_id: UUID | str,
    permission: str | None = None,
) -> AsyncIterator[Any]:
    """Stop an existing stream when its account or resource access is revoked."""
    user_id = access_context().user_id
    try:
        async for event in source:
            async with DatabaseConnection() as connection:
                user = await connection.get(User, user_id) if user_id else None
                if user is None or user.deleted_at is not None:
                    return
                access = await load_access(user, connection)
            if permission and not allows(access, permission):
                return
            grants = access.servers if kind == 'server' else access.databases
            if not access.admin and str(public_id) not in grants:
                return
            yield event
    finally:
        close = getattr(source, 'aclose', None)
        if close:
            await close()
