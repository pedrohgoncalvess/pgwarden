"""Verify statement intervals remain separate from sampled activity."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.databases.analytics.query.summaries import summarize_queries


START = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)


def _row(**values: object) -> SimpleNamespace:
    return SimpleNamespace(**{
        "query": "select * from users", "query_hash": "users",
        "pg_query_id": 123, "source": "statements", "delta_valid": True,
        "execution_count": 120, "duration_count": 120, "duration_sum": 6000,
        "duration_min": None, "duration_max": None, "user_name": "alice",
        "application_name": None, "first_seen": START,
        "last_seen": START + timedelta(seconds=60), "bucket": None,
        **values,
    })


def _summarize(rows: list, search: list | None = None) -> tuple:
    return summarize_queries(rows, lambda text: text, search or [], [], None,
                             "executions", "desc")


def test_statements_provide_counts_and_average_for_actual_interval() -> None:
    """Aggregate users sharing an interval without losing its boundaries."""
    _, timeline, _ = _summarize([_row(), _row(user_name="bob")])
    assert len(timeline) == 1
    point = timeline[0]
    assert point.source == "statements"
    assert point.interval_start == START
    assert point.timestamp == START + timedelta(seconds=60)
    assert point.execution_count == 240
    assert point.avg_duration_ms == 50


def test_mixed_sources_are_never_added_together() -> None:
    """Keep activity visible while statements supply the query totals."""
    activity = _row(source="activity", execution_count=3, duration_count=3,
                    duration_sum=60, bucket=int(START.timestamp() / 300))
    items, timeline, _ = _summarize([_row(), activity])
    assert items[0].execution_count == 120
    assert {point.source: point.execution_count for point in timeline} == {
        "activity": 3, "statements": 120,
    }
    assert next(p for p in timeline if p.source == "activity").interval_start is None


def test_invalid_intervals_are_omitted_and_zero_calls_are_preserved() -> None:
    """A missing baseline or reset is a gap, while a valid zero is data."""
    _, timeline, _ = _summarize([
        _row(delta_valid=False),
        _row(first_seen=START + timedelta(seconds=60),
             last_seen=START + timedelta(seconds=120),
             execution_count=0, duration_count=0, duration_sum=0),
    ])
    assert len(timeline) == 1
    assert timeline[0].execution_count == 0
    assert timeline[0].avg_duration_ms is None
    assert timeline[0].interval_start == START + timedelta(seconds=60)


def test_distinct_boundaries_and_query_filters_are_preserved() -> None:
    """Do not merge staggered intervals or include queries excluded by search."""
    rows = [_row(), _row(first_seen=START + timedelta(seconds=10)),
            _row(query="delete from logs", pg_query_id=456, query_hash="logs")]
    _, timeline, _ = _summarize(rows, ["users"])
    assert len(timeline) == 2
    assert {point.interval_start for point in timeline} == {
        START, START + timedelta(seconds=10),
    }
    assert all(point.execution_count == 120 for point in timeline)
