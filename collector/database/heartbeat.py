"""Collector service heartbeat storage."""

from psycopg import AsyncConnection
from database.load import load_storage_query


async def touch_heartbeat(connection: AsyncConnection) -> None:
    """Record that the collector completed a service cycle."""
    async with connection.cursor() as cursor:
        await cursor.execute(load_storage_query("base", "service_heartbeat", "INSERT"))
