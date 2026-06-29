from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.analytics.models import (
    AnalyticsDataResponse,
    DatabaseSizePoint,
    TableSizePoint,
    AnalyticsTableFilterItem,
)
from app.schemas.exceptions import DatabaseNotFoundError
from database.models.metadata.database import Database
from database.models.metadata.table import Table
from database.models.metric.database_stat import DatabaseStat
from database.models.metric.table import TableMetric


PRESET_RANGES = {
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
    "2w": timedelta(weeks=2),
    "1m": timedelta(days=30),
}


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _resolve_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    preset: Optional[str],
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    end_dt = _parse_iso_datetime(end_date) or now

    if start_date:
        start_dt = _parse_iso_datetime(start_date) or (now - timedelta(days=7))
    elif preset and preset in PRESET_RANGES:
        start_dt = end_dt - PRESET_RANGES[preset]
    else:
        start_dt = end_dt - timedelta(days=7)

    return start_dt, end_dt


async def get_analytics_data(
    db: AsyncSession,
    database_id: UUID,
    start_date: Optional[str],
    end_date: Optional[str],
    preset: Optional[str],
    table_ids: Optional[List[int]],
) -> AnalyticsDataResponse:
    db_result = await db.execute(
        select(Database).where(
            Database.public_id == database_id,
            Database.deleted_at.is_(None),
        )
    )
    database = db_result.scalar_one_or_none()
    if not database:
        raise DatabaseNotFoundError(str(database_id))

    start_dt, end_dt = _resolve_date_range(start_date, end_date, preset)

    # Tables for filter + mapping
    tables_result = await db.execute(
        select(Table.id, Table.schema_name, Table.name)
        .where(
            Table.database_id == database.id,
            Table.deleted_at.is_(None),
        )
        .order_by(Table.schema_name, Table.name)
    )
    tables = [
        AnalyticsTableFilterItem(id=row[0], schema_name=row[1], name=row[2])
        for row in tables_result.all()
    ]

    # Database size history
    db_size_result = await db.execute(
        select(DatabaseStat.collected_at, DatabaseStat.db_size_bytes)
        .where(
            and_(
                DatabaseStat.database_id == database.id,
                DatabaseStat.collected_at >= start_dt,
                DatabaseStat.collected_at <= end_dt,
                DatabaseStat.db_size_bytes.isnot(None),
            )
        )
        .order_by(DatabaseStat.collected_at)
    )
    database_size_history = [
        DatabaseSizePoint(collected_at=row[0], size_bytes=row[1])
        for row in db_size_result.all()
    ]

    # Table size history
    filters = [
        TableMetric.table_id.in_([t.id for t in tables]),
        TableMetric.collected_at >= start_dt,
        TableMetric.collected_at <= end_dt,
        TableMetric.table_size_bytes.isnot(None),
    ]
    if table_ids:
        filters.append(TableMetric.table_id.in_(table_ids))

    table_size_result = await db.execute(
        select(TableMetric.collected_at, TableMetric.table_id, Table.schema_name, Table.name, TableMetric.table_size_bytes)
        .join(Table, Table.id == TableMetric.table_id)
        .where(and_(*filters))
        .order_by(TableMetric.collected_at, Table.schema_name, Table.name)
    )
    table_size_history = [
        TableSizePoint(
            collected_at=row[0],
            table_id=row[1],
            schema_name=row[2],
            table_name=row[3],
            size_bytes=row[4],
        )
        for row in table_size_result.all()
    ]

    return AnalyticsDataResponse(
        database_id=database_id,
        database_name=database.db_name,
        database_size_history=database_size_history,
        table_size_history=table_size_history,
        tables=tables,
    )
