from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

@pytest.fixture
def collect_query_workload():
    # Collector modules load backend-specific queries at import time. Import
    # after each test's storage setup, not while pytest collects all modules.
    from collector.collectors.metric.query_workload import collect_query_workload
    return collect_query_workload


class SimpleContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        return False


def connection(cursor):
    db = AsyncMock()
    session = db.__aenter__.return_value
    session.cursor = lambda **kwargs: SimpleContext(cursor)
    return db, session


@pytest.mark.asyncio
async def test_missing_extension_does_not_write_metrics(collect_query_workload):
    cursor = AsyncMock()
    cursor.fetchone.return_value = None
    monitored, _ = connection(cursor)
    storage = AsyncMock()
    from collector.collectors.metric.query_workload import StatementSourceUnavailable
    with pytest.raises(StatementSourceUnavailable, match='not installed'):
        await collect_query_workload(monitored, storage, 1)
    storage.__aenter__.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_extension_does_not_break_collection(monkeypatch, collect_query_workload):
    cursor = AsyncMock()
    cursor.execute.side_effect = RuntimeError('insufficient privileges')
    monitored, _ = connection(cursor)
    logger = SimpleNamespace(info=AsyncMock())
    monkeypatch.setattr('collector.collectors.metric.query_workload.logger', logger)
    storage = AsyncMock()
    with pytest.raises(RuntimeError, match='insufficient privileges'):
        await collect_query_workload(monitored, storage, 1)
    storage.__aenter__.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshots_preserve_counter_identity_and_reset_epoch(monkeypatch, collect_query_workload):
    cursor = AsyncMock()
    cursor.fetchone.return_value = {'nspname': 'extension schema'}
    reset = datetime(2026, 10, 31, tzinfo=timezone.utc)
    cursor.fetchall.return_value = [{'queryid': -123, 'userid': 10, 'toplevel': True,
        'calls': 200, 'total_exec_time': 1234.5, 'shared_blks_read': 5, 'shared_blks_hit': 30,
        'stats_reset': reset, 'dealloc': 2, 'query': 'SELECT $1', 'query_hash': 'abc',
        'user_name': 'alice', 'rows': 200, 'wal_bytes': 12}]
    monitored, _ = connection(cursor)
    output = AsyncMock()
    storage, session = connection(output)
    monkeypatch.setattr('collector.collectors.metric.query_workload.load_storage_query', lambda *args: 'INSERT')
    assert await collect_query_workload(monitored, storage, 7) == 1
    values = output.executemany.await_args.args[1]
    assert values[0]['database_id'] == 7
    assert values[0]['query_id'] == -123
    assert values[0]['stats_reset'] == reset
    assert values[0]['dealloc'] == 2
    assert values[0]['query'] == 'SELECT $1'
    assert values[0]['rows'] == 200
    assert values[0]['wal_bytes'] == '12'
    assert 'statement_data' not in values[0]
    assert values[0]['collected_at'].tzinfo is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_workload_collector_runs_without_activity(monkeypatch, collect_query_workload):
    from collector.collectors.metric.query_workload import QueryWorkloadMetricCollector
    collect = AsyncMock(return_value=12)
    monkeypatch.setattr('collector.collectors.metric.query_workload.collect_query_workload', collect)
    collector = QueryWorkloadMetricCollector('monitored', 'storage', 1)
    collector._reset_failures = AsyncMock()
    result = await collector._collect()
    assert result.inserted == 12
    collect.assert_awaited_once_with('monitored', 'storage', 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('sqlstate,message,missing', [
    ('42P01', 'relation pg_stat_statements does not exist', True),
    ('55000', 'pg_stat_statements must be loaded via shared_preload_libraries', True),
    ('42501', 'permission denied', False),
    ('08006', 'connection lost', False),
])
async def test_only_missing_statement_sources_are_classified_for_auto_disable(collect_query_workload, sqlstate, message, missing):
    from collector.collectors.metric.query_workload import StatementSourceUnavailable
    error = type('DatabaseError', (RuntimeError,), {'sqlstate': sqlstate})(message)
    cursor = AsyncMock()
    cursor.fetchone.return_value = {'nspname': 'public'}
    cursor.execute.side_effect = [None, error]
    monitored, _ = connection(cursor)
    with pytest.raises(StatementSourceUnavailable if missing else type(error)):
        await collect_query_workload(monitored, AsyncMock(), 1)
