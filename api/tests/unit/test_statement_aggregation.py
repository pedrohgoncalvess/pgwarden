"""Compare compact PostgreSQL aggregation against raw snapshot semantics."""

import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable
from statement_fixtures import insert_samples

from app.databases.analytics.query import sources
from app.databases.analytics.query.models import QueryAnalyticsFilters
from app.databases.analytics.query.services import _normalize_query
from app.databases.analytics.query.statement_aggregation import fetch_compact_statements
from app.databases.analytics.query.summaries import summarize_queries
from app.databases.analytics.query.workload import fetch_statement_groups
from database.models.metric.query_workload import QueryWorkloadMetric as Workload, StatementText

START = datetime(2026, 11, 12, 10, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def statement_engine():
    """Use an isolated disposable database, never the application database."""
    dsn = os.environ.get("PGWARDEN_ANALYTICS_TEST_DSN")
    if not dsn:
        pytest.skip("Set PGWARDEN_ANALYTICS_TEST_DSN to a disposable PostgreSQL server")
    name = "statement_aggregation_" + uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    options = psycopg.conninfo.conninfo_to_dict(dsn) | {"dbname": name}
    engine = create_engine("postgresql+psycopg://", connect_args=options)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE SCHEMA metric")
            for table in (StatementText.__table__, Workload.__table__):
                conn.execute(CreateTable(table, include_foreign_key_constraints=[]))
        yield engine
    finally:
        engine.dispose()
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def statement_session(statement_engine):
    """Roll back each test's fixture data."""
    with statement_engine.connect() as conn:
        transaction = conn.begin()
        with Session(conn) as session:
            yield session
        transaction.rollback()


def _sample(offset: int, **values: object) -> dict:
    return {
        "database_id": 1, "query_id": 123, "user_id": 10, "is_toplevel": True,
        "collected_at": START + timedelta(minutes=offset),
        "calls": 100 + offset * 10, "total_exec_time": 1000 + offset * 20,
        "shared_blks_read": offset, "shared_blks_hit": 100 + offset,
        "stats_reset": START, "dealloc": 0, "query": "SELECT * FROM users",
        "query_hash": "users", "user_name": "alice", "stats_since": None,
    } | values


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {}, {"calls": 1}, {"total_exec_time": 1}, {"shared_blks_read": -1},
    {"shared_blks_hit": 0}, {"stats_reset": None}, {"dealloc": 2},
    {"stats_since": START + timedelta(seconds=1)},
])
@pytest.mark.parametrize("search,exclude,user", [
    ([], [], None), (["users"], [], "alice"), ([], ["users"], None),
])
async def test_compact_response_matches_snapshots(
    statement_session, monkeypatch, change, search, exclude, user,
):
    """Preserve invalid intervals, identities, filters, zero calls and text variants."""
    rows = [_sample(0), _sample(1, **change), _sample(2),
            _sample(3, calls=120, total_exec_time=1040),
            _sample(0, user_id=20, user_name="bob"),
            _sample(1, user_id=20, user_name="bob"),
            _sample(0, query_id=456, query="DELETE FROM logs", query_hash="logs"),
            _sample(1, query_id=456, query="DELETE FROM logs", query_hash="logs"),
            _sample(0, is_toplevel=False), _sample(1, is_toplevel=False),
            _sample(0, database_id=2), _sample(1, database_id=2)]
    insert_samples(statement_session, rows)
    db = AsyncMock(execute=AsyncMock(side_effect=statement_session.execute))
    old = await fetch_statement_groups(db, 1, START, START + timedelta(hours=1), user)
    expected = summarize_queries(old, _normalize_query, search, exclude, 1, "executions", "desc")
    monkeypatch.setattr(sources, "fetch_query_groups", AsyncMock(return_value=([], QueryAnalyticsFilters(users=[], applications=[], states=[]))))
    items, timeline, total, _ = await sources.fetch_analytics(
        db, 1, START, START + timedelta(hours=1), user, None, None,
        _normalize_query, search, exclude, 1, "executions", "desc",
    )
    actual_items = [item.model_dump() for item in items]
    expected_items = [item.model_dump() for item in expected[0]]
    for item in actual_items + expected_items:
        item["user_breakdown"].sort(key=lambda value: value["user_name"] or "")
    assert actual_items == expected_items
    assert [point.model_dump() for point in timeline] == [point.model_dump() for point in expected[1]]
    assert total == expected[2]


@pytest.mark.asyncio
async def test_summary_transfer_is_independent_of_snapshot_count(statement_session):
    """A thousand snapshots of one SQL text return one summary to Python."""
    insert_samples(statement_session, [_sample(i) for i in range(1000)])
    db = AsyncMock(execute=AsyncMock(side_effect=statement_session.execute))
    groups = await fetch_compact_statements(db, 1, START, START + timedelta(days=1), None)
    assert len(groups) == 1
    assert groups[0].execution_count == 9990
    assert "statement_data" not in groups[0]._mapping


def test_storage_has_no_serialized_statistics(statement_session):
    insert_samples(statement_session, [_sample(0), _sample(1)])
    assert "statement_data" not in Workload.__table__.c
    assert "query" not in Workload.__table__.c
    assert statement_session.execute(text("SELECT count(*) FROM metric.statement_text")).scalar_one() == 1


@pytest.mark.asyncio
async def test_application_filter_does_not_include_statements(monkeypatch):
    """Statement counters cannot satisfy a session application filter."""
    monkeypatch.setattr(sources, "fetch_query_groups", AsyncMock(return_value=([], QueryAnalyticsFilters(users=[], applications=[], states=[]))))
    fetch = AsyncMock()
    monkeypatch.setattr(sources, "fetch_compact_statements", fetch)
    response = await sources.fetch_analytics(
        SimpleNamespace(), 1, START, START, None, "app", None,
        _normalize_query, [], [], 50, "executions", "desc",
    )
    assert response[:3] == ([], [], 0)
    fetch.assert_not_awaited()

