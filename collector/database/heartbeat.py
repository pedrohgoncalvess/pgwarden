"""Collector service heartbeat storage."""

from psycopg import AsyncConnection


async def touch_heartbeat(connection: AsyncConnection) -> None:
    """Record that the collector completed a service cycle."""
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO base.service_heartbeat (service)
            VALUES ('collector')
            ON CONFLICT (service) DO UPDATE SET updated_at = now()
            """
        )
