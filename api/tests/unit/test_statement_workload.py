"""Real SQL snapshots, mixed origins, and invalid counter epochs."""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.databases.analytics.query.services import _normalize_query, _statement_context
from app.databases.analytics.query.summaries import summarize_queries
from app.databases.analytics.query.workload import fetch_statement_groups, snapshots, valid_delta
from database.models.metric.query_workload import QueryWorkloadMetric as Workload
from app.ingestion.catalog import validate_statement_data

NOW = datetime(2026, 11, 1, 12)


@pytest.mark.parametrize('value', ['invalid', '[]', 'null', '123'])
def test_ingestion_rejects_malformed_statement_statistics(value):
    with pytest.raises(ValueError, match='JSON object'):
        validate_statement_data(value)


@pytest.fixture
def workload_session():
    engine = create_engine('sqlite://')
    with engine.connect() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS metric")
        conn.exec_driver_sql('''CREATE TABLE metric.query_workload (
            collected_at DATETIME, database_id BIGINT, query_id BIGINT, user_id BIGINT,
            is_toplevel BOOLEAN, calls BIGINT, total_exec_time FLOAT,
            shared_blks_read BIGINT, shared_blks_hit BIGINT, stats_reset DATETIME,
            dealloc BIGINT, query TEXT, query_hash TEXT, user_name TEXT, statement_data TEXT)''')
        with Session(conn) as session:
            yield session
    engine.dispose()


def sample(offset=0, **values):
    return dict(collected_at=NOW + timedelta(minutes=offset), database_id=1,
                query_id=-123, user_id=10, is_toplevel=True, calls=100 + offset * 10,
                total_exec_time=1000 + offset * 100, shared_blks_read=offset,
                shared_blks_hit=100 + offset, stats_reset=NOW, dealloc=0,
                query='SELECT * FROM users WHERE id = $1', query_hash='statement-hash',
                user_name='alice', statement_data='{"wal_bytes": 100}') | values


async def groups(session, start=NOW):
    return await fetch_statement_groups(AsyncMock(execute=AsyncMock(side_effect=session.execute)),
                                       1, start, NOW + timedelta(hours=1))


def activity(**values):
    return SimpleNamespace(pg_query_id=-123, query='SELECT * FROM users WHERE id = 42',
                           query_hash='activity-hash', source='activity', user_name='alice',
                           application_name='app', execution_count=2, duration_count=2,
                           duration_sum=100, duration_min=40, duration_max=60,
                           first_seen=NOW, last_seen=NOW + timedelta(minutes=1),
                           bucket=NOW.timestamp() // 300, **values)


@pytest.mark.asyncio
async def test_statements_only_enter_catalog_without_fabricating_first_interval(workload_session):
    workload_session.execute(Workload.__table__.insert(), [sample()])
    rows = await groups(workload_session)
    items, timeline, total = summarize_queries(rows, _normalize_query, [], [], 50, 'executions', 'desc')
    assert total == 1 and items[0].execution_count == 0
    assert items[0].statements_calls is None
    assert items[0].metrics_source == 'unavailable'
    assert items[0].sources == ['statements']
    assert timeline == []


@pytest.mark.asyncio
async def test_merge_preserves_both_texts_and_does_not_add_activity_counts(workload_session):
    workload_session.execute(Workload.__table__.insert(), [sample(), sample(1)])
    rows = await groups(workload_session)
    items, timeline, total = summarize_queries([activity(), *rows], _normalize_query, [], [], 50, 'executions', 'desc')
    item = items[0]
    assert total == 1
    assert item.execution_count == 10 and item.activity_executions == 2
    assert item.avg_duration_ms == 10 and item.total_duration_ms == 100
    assert item.min_duration_ms is None and item.max_duration_ms is None
    assert item.query_hash == 'pg:-123' and item.pg_query_id == '-123'
    assert item.sources == ['activity', 'statements']
    assert set(item.query_hashes) == {'activity-hash', 'statement-hash'}
    assert len(item.query_texts) == 2
    assert timeline[0].execution_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', [
    {'calls': 1}, {'total_exec_time': 1}, {'shared_blks_read': -1},
    {'stats_reset': NOW + timedelta(seconds=1)}, {'dealloc': 1},
    {'statement_data': json.dumps({'stats_since': 'new epoch'})},
])
async def test_reset_eviction_and_counter_decrease_invalidate_interval(workload_session, changed):
    workload_session.execute(Workload.__table__.insert(), [sample(), sample(1, **changed)])
    rows = await snapshots(AsyncMock(execute=AsyncMock(side_effect=workload_session.execute)),
                           1, NOW, NOW + timedelta(hours=1))
    assert not valid_delta(rows[1])
    items, _, _ = summarize_queries(await groups(workload_session), _normalize_query, [], [], 50, 'executions', 'desc')
    assert items[0].statements_calls is None


@pytest.mark.asyncio
async def test_counters_are_partitioned_by_role_and_level(workload_session):
    workload_session.execute(Workload.__table__.insert(), [
        sample(), sample(1), sample(user_id=20), sample(1, user_id=20),
        sample(is_toplevel=False), sample(1, is_toplevel=False),
        sample(database_id=2), sample(1, database_id=2),
    ])
    items, _, _ = summarize_queries(await groups(workload_session), _normalize_query, [], [], 50, 'executions', 'desc')
    assert items[0].statements_calls == 20


@pytest.mark.asyncio
async def test_interval_crossing_requested_window_is_not_attributed(workload_session):
    workload_session.execute(Workload.__table__.insert(), [sample(), sample(2)])
    items, _, _ = summarize_queries(await groups(workload_session, NOW + timedelta(minutes=1)),
                                   _normalize_query, [], [], 50, 'executions', 'desc')
    assert items[0].statements_calls is None


def test_distinct_postgres_identities_do_not_merge_even_with_equal_sql():
    first = activity()
    second = activity()
    second.pg_query_id = 456
    items, _, total = summarize_queries([first, second], _normalize_query, [], [], 50, 'executions', 'desc')
    assert total == 2
    assert {item.query_hash for item in items} == {'pg:-123', 'pg:456'}


@pytest.mark.asyncio
async def test_snapshot_context_preserves_role_and_execution_level(workload_session):
    workload_session.connection().exec_driver_sql("ATTACH DATABASE ':memory:' AS analytics")
    workload_session.connection().exec_driver_sql('CREATE TABLE analytics.query (id INTEGER, database_id INTEGER, pg_query_id BIGINT, hash TEXT)')
    workload_session.execute(Workload.__table__.insert(), [
        sample(statement_data='{"tag": "first"}'),
        sample(user_id=20, user_name='other', statement_data='{"tag": "top"}'),
        sample(user_id=20, user_name='other', is_toplevel=False, statement_data='{"tag": "nested"}'),
    ])
    db = AsyncMock(execute=AsyncMock(side_effect=workload_session.execute))
    context = await _statement_context(db, SimpleNamespace(id=1), 'pg:-123', -123, NOW, 20, False)
    assert context.execution.source == 'statements'
    assert context.execution.statement_data['tag'] == 'nested'
    assert context.execution.user_name == 'other'
    assert context.execution.duration_ms is None
    assert context.database_connections.active is None
    assert context.locks == [] and context.server_metrics.cpu_percent is None
