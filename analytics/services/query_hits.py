from collections import defaultdict

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.database import DatabaseConnection
from analytics.database.models.analytics import Query, QueryColumnHit, QueryTableHit
from analytics.database.models.metadata import ColumnModel, Table
from analytics.database.models.metric import NativeQueryMetric
from analytics.parser import ColumnMeta, TableMeta, parse_postgres_query


async def process_pending_native_queries(limit: int = 500) -> int:
    async with DatabaseConnection() as session:
        return await process_pending_native_queries_with_session(session, limit=limit)


async def process_pending_native_queries_with_session(session: AsyncSession, limit: int = 500) -> int:
    native_queries = await _pending_queries(session, limit)
    if not native_queries:
        return 0

    metadata_by_database: dict[int, list[TableMeta]] = {}
    processed_query_ids: set[int] = set()
    processed = 0

    for native_query in native_queries:
        if not native_query.query:
            continue

        query_id = await _get_or_create_query_id(session, native_query)
        if query_id is None or query_id in processed_query_ids:
            continue

        if await _has_hits(session, query_id):
            processed_query_ids.add(query_id)
            continue

        database_id = native_query.database_id
        if database_id not in metadata_by_database:
            metadata_by_database[database_id] = await _metadata_for_database(session, database_id)

        parsed = parse_postgres_query(native_query.query, metadata_by_database[database_id])
        await _replace_hits(session, query_id, parsed)
        processed_query_ids.add(query_id)
        processed += 1

    await session.commit()
    return processed


async def _pending_queries(session: AsyncSession, limit: int) -> list[NativeQueryMetric]:
    result = await session.execute(
        select(NativeQueryMetric)
        .where(NativeQueryMetric.query.is_not(None))
        .order_by(NativeQueryMetric.collected_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _metadata_for_database(session: AsyncSession, database_id: int) -> list[TableMeta]:
    table_result = await session.execute(
        select(Table)
        .where(Table.database_id == database_id)
        .where(Table.deleted_at.is_(None))
        .order_by(Table.schema_name.asc(), Table.name.asc())
    )
    tables = list(table_result.scalars().all())
    if not tables:
        return []

    table_ids = [table.id for table in tables]
    column_result = await session.execute(
        select(ColumnModel)
        .where(ColumnModel.table_id.in_(table_ids))
        .where(ColumnModel.deleted_at.is_(None))
        .order_by(ColumnModel.table_id.asc(), ColumnModel.ordinal_position.asc())
    )
    columns_by_table: dict[int, list[ColumnMeta]] = defaultdict(list)
    for column in column_result.scalars().all():
        columns_by_table[column.table_id].append(
            ColumnMeta(
                id=column.id,
                name=column.name,
                fk_table_id=column.fk_table_id,
                fk_column_id=column.fk_column_id,
            )
        )

    return [
        TableMeta(
            id=table.id,
            schema_name=table.schema_name,
            name=table.name,
            columns=tuple(columns_by_table.get(table.id, [])),
        )
        for table in tables
    ]


async def _get_or_create_query_id(session: AsyncSession, native_query: NativeQueryMetric) -> int | None:
    result = await session.execute(select(Query.id).where(Query.query == native_query.query))
    query_id = result.scalar_one_or_none()
    if query_id is not None:
        return query_id

    result = await session.execute(
        insert(Query)
        .values(
            database_id=native_query.database_id,
            query=native_query.query,
            user_name=native_query.user_name,
            application_name=native_query.application_name,
            hash=native_query.query_hash or "",
        )
        .returning(Query.id)
    )
    return result.scalar_one()


async def _has_hits(session: AsyncSession, query_id: int) -> bool:
    result = await session.execute(select(QueryTableHit.id).where(QueryTableHit.query_id == query_id).limit(1))
    return result.scalar_one_or_none() is not None


async def _replace_hits(session: AsyncSession, query_id: int, parsed) -> None:
    await session.execute(delete(QueryTableHit).where(QueryTableHit.query_id == query_id))
    await session.execute(delete(QueryColumnHit).where(QueryColumnHit.query_id == query_id))

    for table in parsed.tables:
        session.add(
            QueryTableHit(
                query_id=query_id,
                schema_name=table.schema_name,
                table_name=table.table_name,
                alias=table.alias,
                is_foreign=table.is_foreign,
            )
        )

    for column in parsed.columns:
        session.add(
            QueryColumnHit(
                query_id=query_id,
                schema_name=column.schema_name,
                table_name=column.table_name,
                column_name=column.column_name,
                is_selected=column.is_selected,
                is_condition=column.is_condition,
                is_condition_foreign=column.is_condition_foreign,
            )
        )
