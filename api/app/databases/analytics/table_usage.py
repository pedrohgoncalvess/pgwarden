"""Table query-usage views backed by Analytics parser results."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.schemas.exceptions import DatabaseNotFoundError
from database.models.metadata.column import ColumnModel
from database.models.metadata.database import Database
from database.models.metadata.table import Table
from app.databases.analytics.query.aggregation import fetch_query_groups
from app.databases.analytics.query.summaries import summarize_queries
from app.databases.analytics.query.workload import fetch_statement_groups


async def _get_table(db: AsyncSession, database_id: UUID, table_id: UUID) -> tuple[Database, Table]:
    """Resolve a tracked table within a monitored database."""
    database = (
        await db.execute(
            select(Database).where(
                Database.public_id == database_id,
                Database.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if database is None:
        raise DatabaseNotFoundError(str(database_id))

    table = (
        await db.execute(
            select(Table).where(
                Table.public_id == table_id,
                Table.database_id == database.id,
                Table.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if table is None:
        raise DatabaseNotFoundError(str(database_id))
    return database, table


async def get_table_usage_available(
    db: AsyncSession, database_id: UUID, table_id: UUID
) -> bool:
    """Return whether Analytics has captured query data for the database."""
    database, _table = await _get_table(db, database_id, table_id)
    result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM analytics.query
                WHERE database_id = :database_id
            )
            """
        ),
        {
            "database_id": database.id,
        },
    )
    return bool(result.scalar())


async def get_table_usage(
    db: AsyncSession, database_id: UUID, table_id: UUID
) -> list[dict[str, str | int | float | datetime | None]]:
    """Return captured query usage for a table, ordered by latest execution."""
    database, table = await _get_table(db, database_id, table_id)
    result = await db.execute(
        text(
            """
            SELECT
                query.query AS query,
                query.hash AS query_hash, query.pg_query_id
            FROM analytics.query_table_hit AS hit
            JOIN analytics.query AS query ON query.id = hit.query_id
            WHERE query.database_id = :database_id
              AND hit.schema_name = :schema_name
              AND hit.table_name = :table_name
            GROUP BY query.id, query.query
            """
        ),
        {
            "database_id": database.id,
            "schema_name": table.schema_name,
            "table_name": table.name,
        },
    )
    return await _with_workload(db, database.id, list(result.mappings()))


async def get_column_usage(
    db: AsyncSession,
    database_id: UUID,
    table_id: UUID,
    column_id: UUID,
) -> list[dict[str, str | int | float | bool | datetime | None]]:
    """Return captured query usage for one column of a tracked table."""
    database, table = await _get_table(db, database_id, table_id)
    column = (
        await db.execute(
            select(ColumnModel).where(
                ColumnModel.public_id == column_id,
                ColumnModel.table_id == table.id,
                ColumnModel.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if column is None:
        raise DatabaseNotFoundError(str(database_id))

    result = await db.execute(
        text(
            """
            SELECT
                query.query AS query,
                query.hash AS query_hash, query.pg_query_id,
                BOOL_OR(hit.is_selected) AS is_selected,
                BOOL_OR(hit.is_condition) AS is_condition,
                BOOL_OR(hit.is_condition_foreign) AS is_condition_foreign
            FROM analytics.query_column_hit AS hit
            JOIN analytics.query AS query ON query.id = hit.query_id
            WHERE query.database_id = :database_id
              AND hit.schema_name = :schema_name
              AND hit.table_name = :table_name
              AND hit.column_name = :column_name
            GROUP BY query.id, query.query
            """
        ),
        {
            "database_id": database.id,
            "schema_name": table.schema_name,
            "table_name": table.name,
            "column_name": column.name,
        },
    )
    return await _with_workload(db, database.id, list(result.mappings()))


async def _with_workload(db, database_id, queries):
    if not queries:
        return []
    start, end = datetime(1970, 1, 1, tzinfo=timezone.utc), datetime.now(timezone.utc)
    activity, _ = await fetch_query_groups(db, database_id, start, end, None, None, None)
    statements = await fetch_statement_groups(db, database_id, start, end)
    # Keep exact SQL for legacy identities; PostgreSQL IDs unify literal variants.
    items, _, _ = summarize_queries([*activity, *statements], lambda sql: sql or '', [], [], None, 'executions', 'desc')
    by_id = {int(item.pg_query_id): item for item in items if item.pg_query_id is not None}
    by_hash = {value: item for item in items for value in item.query_hashes}
    result = {}
    for row in queries:
        item = by_id.get(row.pg_query_id) if row.pg_query_id else by_hash.get(row.query_hash)
        pg_identity = row.pg_query_id or (int(item.pg_query_id) if item and item.pg_query_id else None)
        key = ('pg', pg_identity) if pg_identity else ('text', row.query)
        data = dict(row)
        data.update(
            pg_query_id=str(pg_identity) if pg_identity is not None else None,
            execution_count=item.execution_count if item else 0,
            avg_duration_ms=item.avg_duration_ms if item else None,
            last_executed_at=item.last_seen if item else None,
            sources=item.sources if item else [],
            activity_executions=item.activity_executions if item else 0,
            statements_calls=item.statements_calls if item else None,
            metrics_source=item.metrics_source if item else 'unavailable',
        )
        if key in result:
            for flag in ('is_selected', 'is_condition', 'is_condition_foreign'):
                if flag in data:
                    result[key][flag] |= data[flag]
        else:
            result[key] = data
    return sorted(result.values(), key=lambda row: (row['last_executed_at'] or start, row['query']), reverse=True)
