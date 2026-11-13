from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import asyncpg
import pytest

from app.databases.metrics import uptime
from app.databases.models import DatabaseMetricsSummaryResponse, DatabaseStatsResponse


def session_for(server):
    return SimpleNamespace(execute=AsyncMock(side_effect=[
        Mock(scalar_one_or_none=Mock(return_value=SimpleNamespace(server_id=3, db_name="app"))),
        Mock(scalar_one_or_none=Mock(return_value=server)),
    ]))


@pytest.mark.asyncio
async def test_remote_uptime_does_not_read_credentials_or_connect(monkeypatch):
    database_id = uuid4()
    session = session_for(SimpleNamespace(ingestion_project_id=uuid4()))
    connect = AsyncMock(side_effect=AssertionError("Remote targets cannot be connected to"))
    decrypt = Mock(side_effect=AssertionError("Remote credentials must not be read"))
    monkeypatch.setattr(asyncpg, "connect", connect)
    monkeypatch.setattr(uptime, "decrypt", decrypt)

    result = await uptime.get_database_uptime(session, database_id)

    assert result is None
    connect.assert_not_called()
    decrypt.assert_not_called()
    summary = DatabaseMetricsSummaryResponse(
        database_id=database_id,
        stats=DatabaseStatsResponse(
            database_id=database_id, table_count=119, index_count=504,
            view_count=0, size_bytes=123456, index_hit_rate=99.5,
        ),
        uptime=result,
    )
    assert summary.model_dump(mode="json")["uptime"] is None
    assert summary.stats.table_count == 119
    assert summary.stats.size_bytes == 123456


@pytest.mark.asyncio
@pytest.mark.parametrize("naive", [False, True])
async def test_local_uptime_still_uses_target_start_time(monkeypatch, naive):
    now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
    start = now - timedelta(days=1, hours=3, minutes=4)
    if naive:
        start = start.replace(tzinfo=None)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    connection = SimpleNamespace(
        fetchrow=AsyncMock(return_value={"start_time": start}), close=AsyncMock(),
    )
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(asyncpg, "connect", connect)
    monkeypatch.setattr(uptime, "datetime", FixedDatetime)
    monkeypatch.setattr(uptime, "decrypt", lambda value: value)
    monkeypatch.setattr(uptime, "decrypt_or_plain", lambda value: value)
    server = SimpleNamespace(
        ingestion_project_id=None, host="db.internal", port="5432",
        username="monitor", password="test-password", ssl_mode="prefer",
    )
    database_id = uuid4()

    result = await uptime.get_database_uptime(session_for(server), database_id)

    assert result.database_id == database_id
    assert result.uptime_seconds == 97440
    assert result.uptime_formatted == "1d 3h 4m"
    assert result.postmaster_start_time == "2026-11-10T08:56:00+00:00"
    connect.assert_awaited_once_with(
        host="db.internal", port=5432, user="monitor", password="test-password",
        database="app", ssl="prefer",
    )
    connection.close.assert_awaited_once()
