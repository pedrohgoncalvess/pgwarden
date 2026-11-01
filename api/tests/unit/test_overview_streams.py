"""Overview must support credential-free collectors and PostgreSQL INET values."""

import json
from datetime import datetime, timezone
from ipaddress import ip_address
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.databases.native_queries import services as queries
from app.databases.sessions import services as sessions


@pytest.mark.parametrize('address', ['192.0.2.1', '2001:db8::1'])
@pytest.mark.parametrize('serialize', [queries.serialize_row, sessions.serialize_row])
def test_inet_samples_are_json_serializable(address, serialize):
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    row = SimpleNamespace(
        client_addr=ip_address(address), collected_at=now, pid=42,
        _sa_instance_state=object(),
    )
    assert json.loads(json.dumps(serialize(row))) == {
        'client_addr': address, 'collected_at': now.isoformat(), 'pid': 42,
    }


def scalar(value):
    return Mock(scalar_one_or_none=Mock(return_value=value))


def rows(*values):
    return Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=list(values)))))


def connection_factory(monkeypatch, *results):
    session = SimpleNamespace(execute=AsyncMock(side_effect=results))

    class Connection:
        active = 0

        async def __aenter__(self):
            Connection.active += 1
            return session

        async def __aexit__(self, *args):
            Connection.active -= 1

    monkeypatch.setattr(queries, 'DatabaseConnection', Connection)
    monkeypatch.setattr(queries.asyncio, 'sleep', AsyncMock())
    return session, Connection


async def test_remote_queries_use_latest_stored_snapshot_without_credentials(monkeypatch):
    public_id = uuid4()
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    sample = SimpleNamespace(
        database_id=7, collected_at=now, pid=42,
        client_addr=ip_address('2001:db8::1'), query='SELECT 1',
    )
    session, connection = connection_factory(
        monkeypatch,
        scalar(SimpleNamespace(id=7, server_id=3)),
        scalar(SimpleNamespace(ingestion_project_id=uuid4())),
        scalar(now), rows(sample),
        scalar(now), rows(sample, SimpleNamespace(pid=43, query='SELECT 2')),
    )
    connect = AsyncMock(side_effect=AssertionError('Remote servers have no credentials'))
    monkeypatch.setattr(queries.asyncpg, 'connect', connect)
    decrypt = Mock(side_effect=AssertionError('Remote credentials must not be read'))
    monkeypatch.setattr(queries, 'decrypt', decrypt)
    stream = queries.native_query_stream(public_id)
    try:
        event = await anext(stream)
        assert event['event'] == 'native_query'
        assert json.loads(event['data'])[0]['client_addr'] == '2001:db8::1'
        assert connection.active == 0
        # Same-timestamp rows may arrive in separate sender batches.
        updated = await anext(stream)
        assert len(json.loads(updated['data'])) == 2
        assert connection.active == 0
    finally:
        await stream.aclose()
    connect.assert_not_called()
    decrypt.assert_not_called()
    latest_query = session.execute.call_args_list[2].args[0]
    snapshot_query = session.execute.call_args_list[3].args[0]
    assert latest_query.compile().params['database_id_1'] == 7
    assert snapshot_query.compile().params == {'database_id_1': 7, 'collected_at_1': now}


async def test_remote_stream_can_start_empty_and_receive_its_first_sample(monkeypatch):
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    _, connection = connection_factory(
        monkeypatch, scalar(None), scalar(now), rows(SimpleNamespace(pid=42)),
    )
    stream = queries.stored_native_query_stream(7)
    try:
        assert json.loads((await anext(stream))['data']) == []
        assert json.loads((await anext(stream))['data']) == [{'pid': 42}]
        assert connection.active == 0
    finally:
        await stream.aclose()


async def test_stored_stream_recovers_after_database_error(monkeypatch):
    connection_factory(monkeypatch, RuntimeError('store unavailable'), scalar(None))
    stream = queries.stored_native_query_stream(7)
    try:
        assert (await anext(stream))['event'] == 'error'
        assert (await anext(stream)) == {'event': 'native_query', 'data': '[]'}
    finally:
        await stream.aclose()


async def test_session_stream_emits_inet_sample_without_error(monkeypatch):
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    sample = SimpleNamespace(
        collected_at=now, pid=42, client_addr=ip_address('192.0.2.1'),
    )
    _, connection = connection_factory(
        monkeypatch, scalar(7), scalar(sample), rows(sample),
    )
    monkeypatch.setattr(sessions, 'DatabaseConnection', connection)
    stream = sessions.session_stream(uuid4())
    try:
        event = await anext(stream)
        assert event['event'] == 'sessions'
        assert json.loads(event['data'])[0]['client_addr'] == '192.0.2.1'
        assert connection.active == 0
    finally:
        await stream.aclose()


async def test_local_stream_keeps_direct_collection_and_closes_connection(monkeypatch):
    settings = {'host': 'localhost', 'database': 'test', 'user': 'test'}
    monkeypatch.setattr(queries, 'get_monitored_connection_settings', AsyncMock(return_value=settings))
    connection = SimpleNamespace(
        fetch=AsyncMock(return_value=[{'pid': 42, 'query': 'SELECT 1'}]),
        is_closed=Mock(return_value=False), close=AsyncMock(),
    )
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(queries.asyncpg, 'connect', connect)
    stream = queries.native_query_stream(uuid4())
    try:
        event = await anext(stream)
        assert event['event'] == 'native_query'
        assert json.loads(event['data']) == [{'pid': 42, 'query': 'SELECT 1'}]
        connect.assert_awaited_once_with(**settings, timeout=5)
    finally:
        await stream.aclose()
    connection.close.assert_awaited_once()
