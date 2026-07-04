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
    AnalyticsTableFilterForIndex,
    AnalyticsIndexFilterItem,
    IndexMetricPoint,
    IndexAnalyticsKpi,
    IndexAnalyticsTimelinePoint,
    IndexAnalyticsItem,
    IndexAnalyticsResponse,
)
from app.databases.schemas.exceptions import DatabaseNotFoundError
from database.models.metadata.database import Database
from database.models.metadata.table import Table
from database.models.metadata.index import Index
from database.models.metric.database_stat import DatabaseStat
from database.models.metric.table import TableMetric
from database.models.metric.index import IndexMetric


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


def _hit_rate(blks_hit: Optional[int], blks_read: Optional[int]) -> Optional[float]:
    if blks_hit is None or blks_read is None:
        return None
    total = blks_hit + blks_read
    if total <= 0:
        return None
    return round(blks_hit / total, 4)


def _safe_avg(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 4)


async def get_index_analytics(
    db: AsyncSession,
    database_id: UUID,
    start_date: Optional[str],
    end_date: Optional[str],
    preset: Optional[str],
    table_ids: Optional[List[int]],
    index_ids: Optional[List[int]],
    search: Optional[str],
) -> IndexAnalyticsResponse:
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
        AnalyticsTableFilterForIndex(id=row[0], schema_name=row[1], name=row[2])
        for row in tables_result.all()
    ]
    table_id_set = {t.id for t in tables}

    # Indexes for filter + mapping
    index_query = (
        select(
            Index.id,
            Index.table_id,
            Table.schema_name,
            Table.name.label("table_name"),
            Index.name.label("index_name"),
            Index.type.label("index_type"),
            Index.is_unique,
            Index.is_primary,
        )
        .join(Table, Table.id == Index.table_id)
        .where(
            Index.database_id == database.id,
            Index.deleted_at.is_(None),
            Table.deleted_at.is_(None),
        )
    )
    if table_ids:
        valid_table_ids = [tid for tid in table_ids if tid in table_id_set]
        if valid_table_ids:
            index_query = index_query.where(Index.table_id.in_(valid_table_ids))

    index_result = await db.execute(index_query.order_by(Table.schema_name, Table.name, Index.name))
    index_rows = index_result.all()

    index_filter_items = [
        AnalyticsIndexFilterItem(
            id=row[0],
            table_id=row[1],
            schema_name=row[2],
            table_name=row[3],
            index_name=row[4],
            index_type=row[5],
            is_unique=row[6],
            is_primary=row[7],
        )
        for row in index_rows
    ]
    index_id_set = {i.id for i in index_filter_items}

    if index_ids:
        requested_index_ids = set(index_ids)
        index_id_set = index_id_set & requested_index_ids

    # Index metrics history
    metric_filters = [
        IndexMetric.index_id.in_(list(index_id_set)),
        IndexMetric.collected_at >= start_dt,
        IndexMetric.collected_at <= end_dt,
    ]

    metric_result = await db.execute(
        select(
            IndexMetric.collected_at,
            IndexMetric.index_id,
            IndexMetric.size,
            IndexMetric.scan_qt,
            IndexMetric.tup_read_qt,
            IndexMetric.tup_fetch_qt,
            IndexMetric.blks_read,
            IndexMetric.blks_hit,
        )
        .where(and_(*metric_filters))
        .order_by(IndexMetric.collected_at, IndexMetric.index_id)
    )
    metric_rows = metric_result.all()

    # Build history per index
    history_by_index: dict[int, List[IndexMetricPoint]] = {idx_id: [] for idx_id in index_id_set}
    timeline_by_time: dict[datetime, dict[str, int]] = {}
    for row in metric_rows:
        point = IndexMetricPoint(
            collected_at=row[0],
            index_id=row[1],
            size_bytes=row[2],
            scan_qt=row[3],
            tup_read_qt=row[4],
            tup_fetch_qt=row[5],
            blks_read=row[6],
            blks_hit=row[7],
        )
        history_by_index.setdefault(row[1], []).append(point)

        ts = row[0]
        if ts not in timeline_by_time:
            timeline_by_time[ts] = {"size": 0, "scans": 0, "hits": 0, "reads": 0, "count": 0}
        timeline_by_time[ts]["size"] += row[2]
        timeline_by_time[ts]["scans"] += row[3] or 0
        timeline_by_time[ts]["hits"] += row[7] or 0
        timeline_by_time[ts]["reads"] += row[6] or 0
        timeline_by_time[ts]["count"] += 1

    timeline = [
        IndexAnalyticsTimelinePoint(
            collected_at=ts,
            total_size_bytes=agg["size"],
            total_scans=agg["scans"],
            avg_hit_rate=_hit_rate(agg["hits"], agg["reads"]),
        )
        for ts, agg in sorted(timeline_by_time.items())
    ]

    # Build index items
    index_info_by_id = {row[0]: row for row in index_rows}
    items: List[IndexAnalyticsItem] = []
    for idx_id in index_id_set:
        info = index_info_by_id.get(idx_id)
        if not info:
            continue
        history = history_by_index.get(idx_id, [])
        latest = history[-1] if history else None
        first = history[0] if history else None

        hit_rates = [_hit_rate(p.blks_hit, p.blks_read) for p in history]
        avg_hit_rate = _safe_avg(hit_rates)
        total_scans = sum((p.scan_qt or 0) for p in history) if history else None

        item = IndexAnalyticsItem(
            index_id=info[0],
            table_id=info[1],
            schema_name=info[2],
            table_name=info[3],
            index_name=info[4],
            index_type=info[5],
            is_unique=info[6],
            is_primary=info[7],
            latest_size_bytes=latest.size_bytes if latest else 0,
            latest_scan_qt=latest.scan_qt if latest else None,
            latest_tup_read_qt=latest.tup_read_qt if latest else None,
            latest_tup_fetch_qt=latest.tup_fetch_qt if latest else None,
            latest_blks_read=latest.blks_read if latest else None,
            latest_blks_hit=latest.blks_hit if latest else None,
            hit_rate=avg_hit_rate,
            total_scans=total_scans,
            first_seen=first.collected_at if first else None,
            last_seen=latest.collected_at if latest else None,
            history=history,
        )
        items.append(item)

    if search:
        term = search.lower()
        items = [
            item for item in items
            if term in item.index_name.lower()
            or term in item.table_name.lower()
            or term in item.schema_name.lower()
        ]

    # KPIs
    total_size = sum(item.latest_size_bytes for item in items)
    hit_rates_for_kpi = [item.hit_rate for item in items if item.hit_rate is not None]
    avg_hit_rate_kpi = _safe_avg(hit_rates_for_kpi)
    scan_values = [item.latest_scan_qt for item in items if item.latest_scan_qt is not None]
    avg_scan_kpi = round(sum(scan_values) / len(scan_values), 2) if scan_values else None
    unused_indexes = sum(1 for item in items if not item.latest_scan_qt)
    unique_indexes = sum(1 for item in items if item.is_unique)
    primary_indexes = sum(1 for item in items if item.is_primary)

    kpis = IndexAnalyticsKpi(
        total_indexes=len(items),
        total_size_bytes=total_size,
        avg_hit_rate=avg_hit_rate_kpi,
        avg_scan_qt=avg_scan_kpi,
        unused_indexes=unused_indexes,
        unique_indexes=unique_indexes,
        primary_indexes=primary_indexes,
    )

    return IndexAnalyticsResponse(
        database_id=database_id,
        database_name=database.db_name,
        start_at=start_dt,
        end_at=end_dt,
        kpis=kpis,
        timeline=timeline,
        items=items,
        tables=tables,
        indexes=index_filter_items,
    )
