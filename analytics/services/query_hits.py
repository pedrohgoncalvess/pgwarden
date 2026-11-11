from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, delete, exists, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.database import DatabaseConnection
from analytics.database.heartbeat import touch_heartbeat
from analytics.database.models.analytics import Query, QueryColumnHit, QueryTableHit
from analytics.database.models.metadata import ColumnModel, Table
from analytics.database.models.metric import NativeQueryMetric, QueryWorkloadMetric
from analytics.parser import ColumnMeta, TableMeta, parse_postgres_query


@dataclass(frozen=True)
class QueryObservation:
    database_id: int
    query: str
    query_hash: str | None
    query_id: int | None
    user_name: str | None
    application_name: str | None
    collected_at: datetime
    source: str


async def process_pending_native_queries(limit: int = 500) -> int:
    async with DatabaseConnection() as session:
        return await process_pending_native_queries_with_session(session, limit=limit)


async def process_pending_native_queries_with_session(
    session: AsyncSession,
    limit: int = 500,
    database_id: int | None = None,
    commit: bool = True,
) -> int:
    """Parse pending queries, optionally scoped to one database and transaction."""
    native_queries = await _pending_queries(session, limit, database_id)
    if not native_queries:
        return 0

    metadata_by_database: dict[int, list[TableMeta]] = {}
    processed_query_ids: set[int] = set()
    processed = 0

    for native_query in native_queries:
        if not native_query.query:
            continue

        query_id = await _get_or_create_query_id(session, native_query)
        if query_id is None or (query_id in processed_query_ids and native_query.source != "statements"):
            continue

        if native_query.source != "statements" and await _has_hits(session, query_id):
            processed_query_ids.add(query_id)
            continue

        database_id = native_query.database_id
        if database_id not in metadata_by_database:
            metadata_by_database[database_id] = await _metadata_for_database(session, database_id)

        parsed = parse_postgres_query(native_query.query, metadata_by_database[database_id])
        await _replace_hits(session, query_id, parsed)
        processed_query_ids.add(query_id)
        processed += 1

    if commit:
        await touch_heartbeat(session)
        await session.commit()
    return processed


async def _pending_queries(
    session: AsyncSession,
    limit: int,
    database_id: int | None,
) -> list[QueryObservation]:
    sources = []
    for model, source in ((NativeQueryMetric, "activity"), (QueryWorkloadMetric, "statements")):
        pg_id = func.nullif(model.query_id, 0)
        source_seen = Query.seen_activity if source == "activity" else Query.seen_statements
        # Exclude already catalogued identities BEFORE limiting. Otherwise the
        # same recent 500 queries can indefinitely starve the remaining workload.
        known = exists().where(
            Query.database_id == model.database_id,
            source_seen.is_(True),
            or_(
                (pg_id.is_not(None)) & (Query.pg_query_id == pg_id),
                (Query.query == model.query) & pg_id.is_(None),
            ),
        )
        statement = select(
            model.database_id, model.query, model.query_hash, pg_id.label("query_id"),
            model.user_name,
            (NativeQueryMetric.application_name if source == "activity" else literal(None)).label("application_name"),
            model.collected_at, literal(source).label("source"),
        ).where(model.query.is_not(None), model.query != "", ~known)
        if database_id is not None:
            statement = statement.where(model.database_id == database_id)
        sources.append(statement)
    observed = union_all(*sources).subquery()
    ranked = select(observed, func.row_number().over(
        partition_by=(observed.c.database_id, observed.c.source, observed.c.query_id,
                      case((observed.c.query_id.is_(None), observed.c.query))),
        order_by=observed.c.collected_at.desc(),
    ).label("position")).subquery()
    result = await session.execute(select(ranked).where(ranked.c.position == 1)
                                   .order_by(ranked.c.collected_at.asc()).limit(limit))
    return [QueryObservation(**{key: row[key] for key in QueryObservation.__dataclass_fields__})
            for row in result.mappings()]


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


async def _get_or_create_query_id(session: AsyncSession, native_query: QueryObservation) -> int:
    pg_id = native_query.query_id or None
    identity = [(Query.query == native_query.query) & (Query.pg_query_id.is_(None))]
    if pg_id is not None:
        identity.append(Query.pg_query_id == pg_id)
    else:
        identity = [Query.query == native_query.query]
    result = await session.execute(
        select(Query).where(
            Query.database_id == native_query.database_id,
            or_(*identity),
        ).order_by(case((Query.pg_query_id == pg_id, 0), else_=1), Query.id).limit(1)
    )
    query = result.scalar_one_or_none()
    if query is None:
        query = Query(
            database_id=native_query.database_id,
            query=native_query.query,
            user_name=native_query.user_name,
            application_name=native_query.application_name,
            hash=native_query.query_hash or "",
        )
        session.add(query)
    if query.pg_query_id is None:
        query.pg_query_id = pg_id
    if native_query.source == "activity":
        query.seen_activity = True
        query.application_name = native_query.application_name or query.application_name
    else:
        query.seen_statements = True
        # Prefer the representative full SQL for schema analysis. Activity may
        # have been truncated by track_activity_query_size; originals stay in
        # metric.native_query and remain accessible by their query identity.
        query.query = native_query.query
        query.hash = native_query.query_hash or query.hash
    await session.flush()
    return query.id


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
