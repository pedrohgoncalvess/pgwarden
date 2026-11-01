"""Load query schema context with a bounded number of database round trips."""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.databases.analytics.query.models import (
    QueryContextColumn, QueryContextIndex, QueryContextTable,
)
from database.models.analytics.query_table_hit import QueryTableHit
from database.models.base_model import Base
from database.models.metadata.column import ColumnModel
from database.models.metadata.index import Index
from database.models.metadata.table import Table
from database.models.metric.column import ColumnMetric
from database.models.metric.index import IndexMetric
from database.models.metric.table import TableMetric


def _select_latest(
    metadata: type[Base], metric: type[Base], key: str, window_end: datetime,
) -> Select:
    metric_key = getattr(metric, key)
    latest_time = (
        select(func.max(metric.collected_at))
        .where(metric_key == metadata.id, metric.collected_at <= window_end)
        .correlate(metadata)
        .scalar_subquery()
    )
    return select(metadata, metric).outerjoin(
        metric, and_(metric_key == metadata.id, metric.collected_at == latest_time)
    )


async def get_context_tables(
    db: AsyncSession, database_id: int, query_id: int, window_end: datetime,
) -> list[QueryContextTable]:
    """Fetch tables, indexes and columns in three queries, including missing metrics."""
    has_hit = (
        select(QueryTableHit.id)
        .where(
            QueryTableHit.query_id == query_id,
            QueryTableHit.schema_name == Table.schema_name,
            QueryTableHit.table_name == Table.name,
        )
        .exists()
    )
    table_rows = (await db.execute(
        _select_latest(Table, TableMetric, "table_id", window_end).where(
            Table.database_id == database_id, Table.deleted_at.is_(None), has_hit,
        )
    )).all()
    if not table_rows:
        return []

    table_ids = [table.id for table, _ in table_rows]
    index_rows = (await db.execute(
        _select_latest(Index, IndexMetric, "index_id", window_end).where(
            Index.table_id.in_(table_ids), Index.deleted_at.is_(None),
        )
    )).all()
    column_rows = (await db.execute(
        _select_latest(ColumnModel, ColumnMetric, "column_id", window_end).where(
            ColumnModel.table_id.in_(table_ids), ColumnModel.deleted_at.is_(None),
        )
    )).all()

    indexes = defaultdict(list)
    for index, metric in index_rows:
        hit_rate = None
        if metric and metric.blks_hit is not None and metric.blks_read is not None:
            total_blocks = metric.blks_hit + metric.blks_read
            if total_blocks > 0:
                hit_rate = metric.blks_hit / total_blocks
        indexes[index.table_id].append(QueryContextIndex(
            index_id=index.id, index_name=index.name, index_type=index.type,
            definition=index.definition, is_unique=index.is_unique,
            is_primary=index.is_primary, size_bytes=metric.size if metric else None,
            scan_qt=metric.scan_qt if metric else None, hit_rate=hit_rate,
        ))

    columns = defaultdict(list)
    for column, metric in column_rows:
        columns[column.table_id].append(QueryContextColumn(
            column_id=column.id, name=column.name, data_type=column.data_type,
            is_nullable=column.is_nullable,
            n_distinct=metric.n_distinct if metric else None,
            null_fraction=metric.null_fraction if metric else None,
            avg_width=metric.avg_width if metric else None,
        ))

    return [QueryContextTable(
        table_id=table.id, schema_name=table.schema_name, table_name=table.name,
        n_live_tup=metric.n_live_tup if metric else None,
        n_dead_tup=metric.n_dead_tup if metric else None,
        seq_scan=metric.seq_scan if metric else None,
        idx_scan=metric.idx_scan if metric else None,
        last_vacuum=metric.last_vacuum if metric else None,
        last_autovacuum=metric.last_autovacuum if metric else None,
        last_analyze=metric.last_analyze if metric else None,
        last_autoanalyze=metric.last_autoanalyze if metric else None,
        size_bytes=metric.table_size_bytes if metric else None,
        indexes=indexes[table.id], columns=columns[table.id],
    ) for table, metric in table_rows]
