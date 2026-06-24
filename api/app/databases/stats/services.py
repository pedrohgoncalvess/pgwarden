from uuid import UUID

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.models import DatabaseStatsResponse
from database.models.metadata.database import Database
from database.models.metadata.table import Table
from database.models.metadata.index import Index
from database.models.metric.database_stat import DatabaseStat
from app.schemas.exceptions import DatabaseNotFoundError


async def get_database_stats(db: AsyncSession, database_id: UUID) -> DatabaseStatsResponse:
    db_result = await db.execute(
        select(Database).where(Database.public_id == database_id, Database.deleted_at.is_(None))
    )
    database = db_result.scalar_one_or_none()

    if not database:
        raise DatabaseNotFoundError(str(database_id))

    table_count_result = await db.execute(
        select(func.count()).select_from(Table).where(
            Table.database_id == database.id,
            Table.deleted_at.is_(None)
        )
    )
    table_count = table_count_result.scalar_one()

    index_count_result = await db.execute(
        select(func.count()).select_from(Index).where(
            Index.database_id == database.id,
            Index.deleted_at.is_(None)
        )
    )
    index_count = index_count_result.scalar_one()

    stat_result = await db.execute(
        select(DatabaseStat).where(
            DatabaseStat.database_id == database.id
        ).order_by(desc(DatabaseStat.collected_at)).limit(1)
    )
    latest_stat = stat_result.scalar_one_or_none()

    size_bytes = None
    index_hit_rate = None

    if latest_stat:
        size_bytes = latest_stat.db_size_bytes
        total_blks = (latest_stat.blks_hit or 0) + (latest_stat.blks_read or 0)
        if total_blks > 0:
            index_hit_rate = round((latest_stat.blks_hit or 0) / total_blks * 100, 2)

    return DatabaseStatsResponse(
        database_id=database_id,
        table_count=table_count,
        index_count=index_count,
        view_count=0,
        size_bytes=size_bytes,
        index_hit_rate=index_hit_rate,
    )
