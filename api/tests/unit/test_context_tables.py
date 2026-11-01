"""Exercise context SQL against an isolated database without external services."""

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.databases.analytics.query.context_tables import get_context_tables
from database.models.analytics.query_table_hit import QueryTableHit
from database.models.metadata.column import ColumnModel
from database.models.metadata.index import Index
from database.models.metadata.table import Table
from database.models.metric.column import ColumnMetric
from database.models.metric.index import IndexMetric
from database.models.metric.table import TableMetric


@pytest.fixture
def context_session() -> Iterator[Session]:
    """Provide attached schemas in a disposable in-memory SQL database."""
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        for schema in ("metadata", "metric", "analytics"):
            connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {schema}")
        connection.connection.create_function(
            "uuid_generate_v4", 0, lambda: uuid.uuid4().hex,
        )
        for model in (
            Table, Index, ColumnModel, QueryTableHit,
            TableMetric, IndexMetric, ColumnMetric,
        ):
            model.__table__.create(connection)
        with Session(connection) as session:
            yield session
    engine.dispose()


def _add_table(session: Session, table_id: int, **values: object) -> None:
    session.add(Table(
        id=table_id, oid=table_id, database_id=1,
        schema_name="public", name=f"table_{table_id}", **values,
    ))
    session.add(QueryTableHit(
        id=table_id, query_id=1,
        schema_name="public", table_name=f"table_{table_id}",
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("table_count", [1, 20])
async def test_round_trips_do_not_grow_with_schema(
    context_session: Session, table_count: int,
) -> None:
    """Keep round trips constant as the number of schema objects increases."""
    now = datetime(2026, 11, 1)
    for table_id in range(1, table_count + 1):
        _add_table(context_session, table_id)
        for offset in range(5):
            object_id = table_id * 10 + offset
            context_session.add(Index(
                id=object_id, oid=object_id, database_id=1, table_id=table_id,
                name=f"index_{object_id}", type="btree", definition="CREATE INDEX",
            ))
            context_session.add(ColumnModel(
                id=object_id, table_id=table_id, name=f"column_{object_id}",
                data_type="integer", ordinal_position=offset,
            ))
    context_session.flush()
    execute = AsyncMock(side_effect=context_session.execute)
    db = AsyncMock(execute=execute)

    tables = await get_context_tables(db, 1, 1, now)

    assert execute.await_count == 3
    assert len(tables) == table_count
    assert all(len(table.indexes) == 5 for table in tables)
    assert all(len(table.columns) == 5 for table in tables)
    assert all(table.n_live_tup is None for table in tables)


@pytest.mark.asyncio
async def test_preserves_snapshot_and_filters(context_session: Session) -> None:
    """Exclude future metrics, deleted tables, other databases and duplicate hits."""
    now = datetime(2026, 11, 1)
    _add_table(context_session, 1)
    _add_table(context_session, 2, deleted_at=now)
    context_session.add(QueryTableHit(
        id=3, query_id=1, schema_name="public", table_name="table_1",
    ))
    context_session.add(Index(
        id=1, oid=1, database_id=1, table_id=1, name="index_1",
        type="btree", definition="CREATE INDEX",
    ))
    context_session.add(ColumnModel(
        id=1, table_id=1, name="column_1", data_type="integer", ordinal_position=1,
    ))
    context_session.flush()
    for delta, value in ((-2, 10), (-1, 20), (1, 999)):
        stamp = now + timedelta(minutes=delta)
        context_session.add(TableMetric(
            table_id=1, collected_at=stamp, n_live_tup=value,
        ))
        context_session.add(IndexMetric(
            index_id=1, collected_at=stamp, size=value,
            blks_hit=3, blks_read=1,
        ))
        context_session.add(ColumnMetric(
            column_id=1, collected_at=stamp, avg_width=value,
        ))
    context_session.flush()
    db = AsyncMock(execute=AsyncMock(side_effect=context_session.execute))

    tables = await get_context_tables(db, 1, 1, now)

    assert len(tables) == 1
    assert tables[0].n_live_tup == 20
    assert tables[0].indexes[0].size_bytes == 20
    assert tables[0].indexes[0].hit_rate == .75
    assert tables[0].columns[0].avg_width == 20
    assert await get_context_tables(db, 2, 1, now) == []
    assert await get_context_tables(db, 1, 2, now) == []
