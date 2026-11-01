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
    assert await collect_query_workload(monitored, storage, 1) == 0
    storage.__aenter__.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_extension_does_not_break_collection(monkeypatch, collect_query_workload):
    cursor = AsyncMock()
    cursor.execute.side_effect = RuntimeError('insufficient privileges')
    monitored, _ = connection(cursor)
    logger = SimpleNamespace(info=AsyncMock())
    monkeypatch.setattr('collector.collectors.metric.query_workload.logger', logger)
    storage = AsyncMock()
    assert await collect_query_workload(monitored, storage, 1) == 0
    storage.__aenter__.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshots_preserve_counter_identity_and_reset_epoch(monkeypatch, collect_query_workload):
    cursor = AsyncMock()
    cursor.fetchone.return_value = {'nspname': 'extension schema'}
    reset = datetime(2026, 10, 31, tzinfo=timezone.utc)
    cursor.fetchall.return_value = [{'query_id': -123, 'user_id': 10, 'is_toplevel': True,
        'calls': 200, 'total_exec_time': 1234.5, 'shared_blks_read': 5, 'shared_blks_hit': 30,
        'stats_reset': reset, 'dealloc': 2}]
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
    assert values[0]['collected_at'].second == 0
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_workload_collection_is_throttled_even_when_unavailable(monkeypatch, collect_query_workload):
    from collector.collectors.metric.native_query import NativeQueryMetricCollector
    collect = AsyncMock(return_value=0)
    monkeypatch.setattr('collector.collectors.metric.native_query.collect_query_workload', collect)
    monkeypatch.setattr('collector.collectors.metric.native_query.monotonic', iter([0, 1, 61]).__next__)
    collector = NativeQueryMetricCollector(None, None, 1)
    await collector._collect_workload()
    await collector._collect_workload()
    await collector._collect_workload()
    assert collect.await_count == 2
