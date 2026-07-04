from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.models import UptimeResponse
from database.models.metadata.database import Database
from database.models.collector.server import Server
from app.databases.schemas.exceptions import DatabaseNotFoundError
from utils import decrypt, decrypt_or_plain


async def get_database_uptime(db: AsyncSession, database_id: UUID) -> UptimeResponse:
    db_result = await db.execute(
        select(Database).where(Database.public_id == database_id, Database.deleted_at.is_(None))
    )
    database = db_result.scalar_one_or_none()

    if not database:
        raise DatabaseNotFoundError(str(database_id))

    server_result = await db.execute(
        select(Server).where(Server.id == database.server_id, Server.deleted_at.is_(None))
    )
    server = server_result.scalar_one_or_none()

    if not server:
        raise DatabaseNotFoundError(f"Server for database {database_id} not found")

    import asyncpg

    host = decrypt(server.host)
    port = int(decrypt(server.port))
    user = decrypt(server.username)
    password = decrypt(server.password)
    db_name = decrypt_or_plain(database.db_name)

    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
        ssl="prefer" if server.ssl_mode == "prefer" else server.ssl_mode,
    )

    try:
        row = await conn.fetchrow("SELECT pg_postmaster_start_time() as start_time")
        start_time = row["start_time"]
    finally:
        await conn.close()

    now = datetime.now(timezone.utc)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    delta = now - start_time
    uptime_seconds = int(delta.total_seconds())

    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60

    if days > 0:
        uptime_formatted = f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        uptime_formatted = f"{hours}h {minutes}m"
    else:
        uptime_formatted = f"{minutes}m"

    return UptimeResponse(
        database_id=database_id,
        uptime_formatted=uptime_formatted,
        uptime_seconds=uptime_seconds,
        postmaster_start_time=start_time.isoformat(),
    )
