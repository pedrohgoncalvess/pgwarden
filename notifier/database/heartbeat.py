"""Notifier service heartbeat storage."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def touch_heartbeat(session: AsyncSession) -> None:
    """Record that the notifier completed a service cycle."""
    await session.execute(
        text(
            """
            INSERT INTO base.service_heartbeat (service)
            VALUES ('notifier')
            ON CONFLICT (service) DO UPDATE SET updated_at = now()
            """
        )
    )
