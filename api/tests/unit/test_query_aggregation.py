"""Verify SQL aggregation semantics and the amount of data sent to Python."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.databases.analytics.query.aggregation import fetch_query_groups
from app.databases.analytics.query.services import _normalize_query
from app.databases.analytics.query.summaries import summarize_queries
from database.models.metric.native_query import NativeQueryMetric as Sample

NOW = datetime(2026, 11, 1, 12)


@pytest.fixture
def samples_session() -> Iterator[Session]:
    """Provide a real SQL database for the portable aggregation expressions."""
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS metric")
        connection.exec_driver_sql("""
            CREATE TABLE metric.native_query (
                database_id INTEGER, collected_at DATETIME, pid INTEGER,
                backend_start DATETIME, query_start DATETIME, query_hash TEXT,
                query TEXT, query_duration_ms FLOAT, user_name TEXT,
                application_name TEXT, state TEXT, query_id BIGINT,
                PRIMARY KEY (collected_at, database_id, pid, backend_start)
            )
        """)
        with Session(connection) as session:
            yield session
    engine.dispose()


def _sample(pid: int, **values: object) -> dict:
    return {
        "database_id": 1, "collected_at": NOW, "pid": pid,
        "backend_start": NOW - timedelta(hours=1), "query_start": NOW,
        "query_hash": "select", "query": "SELECT * FROM users WHERE id = 1",
        "query_duration_ms": 100, "user_name": "alice",
        "application_name": "app", "state": "active", **values,
    }


async def _fetch(session: Session, **filters: str) -> tuple:
    db = AsyncMock(execute=AsyncMock(side_effect=session.execute))
    return await fetch_query_groups(
        db, 1, NOW - timedelta(minutes=1), NOW + timedelta(days=1),
        filters.get("user_name"), filters.get("application_name"),
        filters.get("state"),
    )


@pytest.mark.asyncio
async def test_sql_compresses_ten_thousand_samples(samples_session: Session) -> None:
    """Transfer one aggregate rather than ten thousand sample rows."""
    samples_session.execute(Sample.__table__.insert(), [
        _sample(pid, collected_at=NOW + timedelta(milliseconds=offset),
                query_duration_ms=offset)
        for pid in range(100) for offset in range(100)
    ])
    groups, _ = await _fetch(samples_session)
    items, timeline, total = summarize_queries(
        groups, _normalize_query, [], [], 10, "executions", "desc",
    )
    assert len(groups) == 1
    assert total == 1
    assert items[0].execution_count == 100
    assert items[0].avg_duration_ms == 49.5
    assert timeline[0].execution_count == 100


@pytest.mark.asyncio
async def test_preserves_weighting_breakdowns_and_snapshot_filters(
    samples_session: Session,
) -> None:
    """Average executions equally even when their snapshot counts differ."""
    samples_session.execute(Sample.__table__.insert(), [
        _sample(1, query_duration_ms=100),
        _sample(1, collected_at=NOW + timedelta(seconds=1),
                query_duration_ms=150, state="idle", user_name="later"),
        _sample(1, collected_at=NOW + timedelta(seconds=2), query_duration_ms=None),
        _sample(2, query_duration_ms=200, user_name="bob", application_name="other"),
        _sample(3, query_duration_ms=None),
        _sample(1, database_id=2, query_duration_ms=9999),
        _sample(4, collected_at=NOW - timedelta(days=2), query_duration_ms=9999),
    ])
    groups, filters = await _fetch(samples_session)
    items, timeline, _ = summarize_queries(
        groups, _normalize_query, [], [], None, "executions", "desc",
    )
    item = items[0]
    assert item.execution_count == 3
    assert item.avg_duration_ms == 162.5
    assert item.total_duration_ms == 325
    assert item.min_duration_ms == 125
    assert item.max_duration_ms == 200
    assert {row.user_name: row.execution_count for row in item.user_breakdown} == {
        "alice": 2, "bob": 1,
    }
    assert item.unique_applications == 2
    assert filters.states == ["active", "idle"]
    assert filters.users == ["alice", "bob", "later"]
    assert timeline[0].avg_duration_ms == 162.5
    assert item.last_seen == NOW + timedelta(seconds=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("order_by", [
    "executions", "avg_duration", "max_duration", "total_duration",
])
async def test_normalization_search_order_and_limit(
    samples_session: Session, order_by: str,
) -> None:
    """Merge equivalent signatures and sort the complete result before limiting."""
    samples_session.execute(Sample.__table__.insert(), [
        _sample(1, query_hash="first", query_duration_ms=100),
        _sample(2, query_hash="second", query="SELECT * FROM users WHERE id = 2"),
        _sample(3, query_hash="delete", query="DELETE FROM logs", query_duration_ms=10),
    ])
    groups, filters = await _fetch(samples_session)
    items, _, total = summarize_queries(
        groups, _normalize_query, [], [], 1, order_by, "desc",
    )
    assert total == 2
    assert len(items) == 1
    assert items[0].execution_count == 2
    ascending, _, _ = summarize_queries(
        groups, _normalize_query, [], [], 1, order_by, "asc",
    )
    assert ascending[0].query_signature == "delete from logs"
    matches, _, total = summarize_queries(
        groups, _normalize_query, ["users", "logs"], ["delete"], 10,
        order_by, "desc",
    )
    assert total == 1
    assert matches[0].query_signature == "select * from users where id = ?"
    assert filters.users == ["alice"]


@pytest.mark.asyncio
async def test_missing_starts_hashes_and_durations(samples_session: Session) -> None:
    """Keep uncorrelated samples and unrelated unhashed statements distinct."""
    samples_session.execute(Sample.__table__.insert(), [
        _sample(1, query_start=None, query_hash=None, query_duration_ms=None),
        _sample(1, query_start=None, query_hash=None, query_duration_ms=None,
                collected_at=NOW + timedelta(seconds=1)),
        _sample(2, query_hash=None, query="DELETE FROM logs", query_duration_ms=None),
    ])
    groups, _ = await _fetch(samples_session)
    items, _, total = summarize_queries(
        groups, _normalize_query, [], [], 10, "executions", "desc",
    )
    assert total == 2
    assert items[0].execution_count == 2
    assert all(item.avg_duration_ms is None for item in items)
    assert all(item.total_duration_ms is None for item in items)


@pytest.mark.asyncio
async def test_filters_apply_before_execution_deduplication(
    samples_session: Session,
) -> None:
    """Use the first matching snapshot and keep empty responses valid."""
    samples_session.execute(Sample.__table__.insert(), [
        _sample(1),
        _sample(1, state="idle", user_name="bob", application_name="other",
                collected_at=NOW + timedelta(seconds=1)),
    ])
    groups, filters = await _fetch(
        samples_session, state="idle", user_name="bob", application_name="other",
    )
    assert len(groups) == 1
    assert groups[0].first_seen == NOW + timedelta(seconds=1)
    assert filters.users == ["bob"]
    empty, choices = await _fetch(samples_session, user_name="absent")
    assert empty == []
    assert choices.users == []
    assert summarize_queries(
        empty, _normalize_query, [], [], 10, "executions", "desc",
    ) == ([], [], 0)


@pytest.mark.asyncio
async def test_timeline_uses_execution_first_seen(samples_session: Session) -> None:
    """Count a sampled execution once in its first bucket even if it spans buckets."""
    later = NOW + timedelta(minutes=6)
    samples_session.execute(Sample.__table__.insert(), [
        _sample(1, query_duration_ms=100, user_name=None, application_name=None),
        _sample(1, collected_at=later, query_duration_ms=300),
        _sample(1, collected_at=later + timedelta(seconds=1),
                query_start=later, query_duration_ms=50),
    ])
    groups, filters = await _fetch(samples_session)
    items, timeline, _ = summarize_queries(
        groups, _normalize_query, [], [], 10, "executions", "desc",
    )
    assert items[0].execution_count == 2
    assert items[0].avg_duration_ms == 125
    assert [point.execution_count for point in timeline] == [1, 1]
    assert [point.avg_duration_ms for point in timeline] == [200, 50]
    assert timeline[0].timestamp.minute == 0
    assert timeline[1].timestamp.minute == 5
    assert filters.users == ["alice", None]
