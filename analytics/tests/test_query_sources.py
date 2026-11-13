"""Both metric sources enter the real parsers and share a query identity."""

from datetime import datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Boolean, DateTime, Float, Integer, BigInteger, create_engine, select
from sqlalchemy.orm import Session

from analytics.database.models.analytics import Query, QueryColumnHit, QueryTableHit
from analytics.database.models.metric import NativeQueryMetric, QueryWorkloadMetric
from analytics.database.models.metric.query_workload import StatementText
from analytics.parser import ColumnMeta, TableMeta
from analytics.services import query_hits
from analytics.services.query_analysis import _analyze_context, _build_statement_context

NOW = datetime(2026, 11, 1, 12)


@pytest.fixture
def sql_session():
    engine = create_engine('sqlite://')
    with engine.connect() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS metric")
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS analytics")
        for model in (StatementText, Query, QueryColumnHit, QueryTableHit, NativeQueryMetric, QueryWorkloadMetric):
            columns = []
            for column in model.__table__.columns:
                if column.name == 'id':
                    ddl = 'INTEGER PRIMARY KEY AUTOINCREMENT'
                elif isinstance(column.type, DateTime):
                    ddl = 'DATETIME'
                elif isinstance(column.type, (Integer, BigInteger, Boolean)):
                    ddl = 'INTEGER'
                elif isinstance(column.type, Float):
                    ddl = 'FLOAT'
                else:
                    ddl = 'TEXT'
                if column.name in ('seen_activity', 'seen_statements'):
                    ddl += ' DEFAULT 0'
                if column.name == 'created_at':
                    ddl += ' DEFAULT CURRENT_TIMESTAMP'
                columns.append(f'"{column.name}" {ddl}')
            conn.exec_driver_sql(f'CREATE TABLE {model.__table__.schema}."{model.__tablename__}" ({", ".join(columns)})')
        with Session(conn) as session:
            yield session
    engine.dispose()


def adapter(session):
    return SimpleNamespace(execute=AsyncMock(side_effect=session.execute),
                           add=session.add, flush=AsyncMock(side_effect=session.flush))


def statement(**values):
    return dict(database_id=1, collected_at=NOW, query_id=123, user_id=10,
                is_toplevel=True, calls=100, total_exec_time=1000,
                shared_blks_read=0, shared_blks_hit=10, dealloc=0,
                query='SELECT id FROM public.users WHERE id = $1',
                query_hash='statement', user_name='alice') | values


def insert_statements(session, rows):
    for values in rows:
        row = dict(values)
        query = row.pop('query')
        query_hash = row.pop('query_hash')
        fingerprint = sha256(query.encode()).hexdigest()
        identity = session.execute(select(StatementText.id).where(
            StatementText.database_id == row['database_id'], StatementText.fingerprint == fingerprint,
        )).scalar_one_or_none()
        if identity is None:
            identity = session.execute(StatementText.__table__.insert().values(
                database_id=row['database_id'],fingerprint=fingerprint,query=query,query_hash=query_hash,
            ).returning(StatementText.id)).scalar_one()
        session.execute(QueryWorkloadMetric.__table__.insert().values(**row,statement_text_id=identity))


def activity(**values):
    return dict(database_id=1, collected_at=NOW + timedelta(seconds=1), pid=1,
                backend_start=NOW, query_id=123,
                query='SELECT id FROM public.users WHERE id = 42',
                query_hash='activity', user_name='alice', application_name='app') | values


@pytest.mark.asyncio
async def test_statements_alone_are_parsed_and_activity_enriches_same_catalog_row(sql_session, monkeypatch):
    metadata = [TableMeta(id=1, schema_name='public', name='users', columns=(ColumnMeta(id=1, name='id'),))]
    monkeypatch.setattr(query_hits, '_metadata_for_database', AsyncMock(return_value=metadata))
    insert_statements(sql_session, [statement()])
    db = adapter(sql_session)
    assert await query_hits.process_pending_native_queries_with_session(db, commit=False) == 1
    query = sql_session.execute(select(Query)).scalar_one()
    assert query.pg_query_id == 123 and query.seen_statements and not query.seen_activity
    hit = sql_session.execute(select(QueryColumnHit)).scalar_one()
    assert hit.column_name == 'id' and hit.is_condition
    sql_session.execute(NativeQueryMetric.__table__.insert(), [activity()])
    await query_hits.process_pending_native_queries_with_session(db, commit=False)
    assert len(sql_session.execute(select(Query)).scalars().all()) == 1
    assert query.seen_activity and query.seen_statements
    assert await query_hits._pending_queries(db, 500, 1) == []


@pytest.mark.asyncio
async def test_backlog_progresses_past_batch_limit(sql_session, monkeypatch):
    monkeypatch.setattr(query_hits, '_metadata_for_database', AsyncMock(return_value=[]))
    insert_statements(sql_session, [statement(query_id=i + 1) for i in range(7)])
    db = adapter(sql_session)
    for expected in (3, 3, 1, 0):
        assert await query_hits.process_pending_native_queries_with_session(db, limit=3, commit=False) == expected
    assert len(sql_session.execute(select(Query)).scalars().all()) == 7


@pytest.mark.asyncio
async def test_same_sql_with_different_postgres_ids_keeps_separate_catalog_entries(sql_session, monkeypatch):
    monkeypatch.setattr(query_hits, '_metadata_for_database', AsyncMock(return_value=[]))
    insert_statements(sql_session, [statement(), statement(query_id=456)])
    await query_hits.process_pending_native_queries_with_session(adapter(sql_session), commit=False)
    assert {q.pg_query_id for q in sql_session.execute(select(Query)).scalars()} == {123, 456}


@pytest.mark.asyncio
async def test_full_statement_text_replaces_truncated_activity_in_parser(sql_session, monkeypatch):
    metadata = [TableMeta(id=1, schema_name='public', name='users', columns=(ColumnMeta(id=1, name='id'),))]
    monkeypatch.setattr(query_hits, '_metadata_for_database', AsyncMock(return_value=metadata))
    sql_session.execute(NativeQueryMetric.__table__.insert(), [activity(query='SELECT id FROM public.users')])
    db = adapter(sql_session)
    await query_hits.process_pending_native_queries_with_session(db, commit=False)
    insert_statements(sql_session, [statement()])
    await query_hits.process_pending_native_queries_with_session(db, commit=False)
    query = sql_session.execute(select(Query)).scalar_one()
    assert query.query.endswith('WHERE id = $1')
    assert sql_session.execute(select(QueryColumnHit)).scalar_one().is_condition


@pytest.mark.asyncio
async def test_missing_query_id_can_be_enriched_after_collection_changes(sql_session, monkeypatch):
    monkeypatch.setattr(query_hits, '_metadata_for_database', AsyncMock(return_value=[]))
    sql_session.execute(NativeQueryMetric.__table__.insert(), [activity(query_id=None)])
    db = adapter(sql_session)
    await query_hits.process_pending_native_queries_with_session(db, commit=False)
    sql_session.execute(NativeQueryMetric.__table__.insert(), [activity(collected_at=NOW + timedelta(seconds=5))])
    await query_hits.process_pending_native_queries_with_session(db, commit=False)
    assert sql_session.execute(select(Query)).scalar_one().pg_query_id == 123


@pytest.mark.asyncio
async def test_statement_analysis_does_not_attribute_cpu_locks_or_execution_duration(sql_session, monkeypatch):
    import analytics.services.query_analysis as analysis
    insert_statements(sql_session, [statement()])
    monkeypatch.setattr(analysis, '_table_insights', AsyncMock(return_value=[]))
    query = SimpleNamespace(id=1, database_id=1, pg_query_id=123, query='SELECT id FROM public.users WHERE id = $1')
    context = await _build_statement_context(adapter(sql_session), query, SimpleNamespace(id=1, server_id=1))
    assert context.source == 'statements'
    assert context.cpu_samples == context.lock_samples == context.duration_history_ms == []
    assert _analyze_context(context) == []
