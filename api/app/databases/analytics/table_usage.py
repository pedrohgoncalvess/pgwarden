"""Table query-usage views backed by Analytics parser results."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.schemas.exceptions import DatabaseNotFoundError
from database.models.metadata.column import ColumnModel
from database.models.metadata.database import Database
from database.models.metadata.table import Table


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
                COUNT(native_query.collected_at) AS execution_count,
                MAX(native_query.collected_at) AS last_executed_at,
                AVG(native_query.query_duration_ms) AS avg_duration_ms
            FROM analytics.query_table_hit AS hit
            JOIN analytics.query AS query ON query.id = hit.query_id
            LEFT JOIN metric.native_query AS native_query
                ON native_query.database_id = :database_id
                AND native_query.query = query.query
            WHERE query.database_id = :database_id
              AND hit.schema_name = :schema_name
              AND hit.table_name = :table_name
            GROUP BY query.id, query.query
            ORDER BY MAX(native_query.collected_at) DESC NULLS LAST, query.query
            """
        ),
        {
            "database_id": database.id,
            "schema_name": table.schema_name,
            "table_name": table.name,
        },
    )
    return [dict(row) for row in result.mappings()]


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
                COUNT(native_query.collected_at) AS execution_count,
                MAX(native_query.collected_at) AS last_executed_at,
                AVG(native_query.query_duration_ms) AS avg_duration_ms,
                BOOL_OR(hit.is_selected) AS is_selected,
                BOOL_OR(hit.is_condition) AS is_condition,
                BOOL_OR(hit.is_condition_foreign) AS is_condition_foreign
            FROM analytics.query_column_hit AS hit
            JOIN analytics.query AS query ON query.id = hit.query_id
            LEFT JOIN metric.native_query AS native_query
                ON native_query.database_id = :database_id
                AND native_query.query = query.query
            WHERE query.database_id = :database_id
              AND hit.schema_name = :schema_name
              AND hit.table_name = :table_name
              AND hit.column_name = :column_name
            GROUP BY query.id, query.query
            ORDER BY MAX(native_query.collected_at) DESC NULLS LAST, query.query
            """
        ),
        {
            "database_id": database.id,
            "schema_name": table.schema_name,
            "table_name": table.name,
            "column_name": column.name,
        },
    )
    return [dict(row) for row in result.mappings()]
