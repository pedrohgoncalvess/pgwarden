"""
Unit tests for the new analytics features added to query_analysis.py:
  - Query regression detection
  - Schema change correlation
  - Selectivity-aware missing index findings
  - Composite index DDL suggestion
  - Lock chain reconstruction
  - Improved _summary()
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from analytics.services.query_analysis import (
    DroppedIndexInfo,
    FindingDraft,
    QueryContext,
    TimeWindow,
    _analyze_context,
    _extract_on_clause,
    _percentile,
    _regression_findings,
    _schema_change_findings,
    _suggest_index_ddl,
    _summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _window(offset_minutes: int = 0) -> TimeWindow:
    base = _now() - timedelta(minutes=offset_minutes)
    return TimeWindow(started_at=base - timedelta(seconds=60), ended_at=base)


def _make_column(col_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=col_id, name=name)


def _make_table(schema: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(schema_name=schema, name=name, id=1)


def _make_column_metric(col_id: int, n_distinct: float | None, null_fraction: float | None) -> SimpleNamespace:
    return SimpleNamespace(column_id=col_id, n_distinct=n_distinct, null_fraction=null_fraction, avg_width=8)


def _base_context(
    duration_history_ms: list[float] | None = None,
    current_duration_ms: float | None = None,
    dropped_indexes: list[DroppedIndexInfo] | None = None,
    tables: list | None = None,
    lock_samples: list | None = None,
    session_samples: list | None = None,
) -> QueryContext:
    window = _window()
    native_query = SimpleNamespace(
        query_duration_ms=current_duration_ms,
        collected_at=window.ended_at,
        pid=1,
        backend_start=window.started_at,
        query_start=None,
        query_hash="abc123",
        database_id=1,
        query="SELECT 1",
        wait_event_type=None,
        wait_event=None,
    )
    return QueryContext(
        query=SimpleNamespace(id=1, database_id=1, hash="abc123", query="SELECT 1"),
        native_query=native_query,
        database=SimpleNamespace(id=1, server_id=10),
        window=window,
        tables=tables or [],
        cpu_samples=[],
        cpu_baseline=[],
        ram_samples=[],
        io_samples=[],
        io_baseline=[],
        disk_samples=[],
        session_samples=session_samples or [],
        lock_samples=lock_samples or [],
        duration_history_ms=duration_history_ms or [],
        recent_dropped_indexes=dropped_indexes or [],
    )


# ---------------------------------------------------------------------------
# _percentile
# ---------------------------------------------------------------------------

def test_percentile_basic():
    assert _percentile([10, 20, 30, 40, 50], 50) == 30
    assert _percentile([10, 20, 30, 40, 50], 95) == 50
    assert _percentile([], 50) == 0.0


# ---------------------------------------------------------------------------
# _extract_on_clause
# ---------------------------------------------------------------------------

def test_extract_on_clause_standard():
    definition = "CREATE INDEX idx_orders_user ON sales.orders (user_id)"
    assert _extract_on_clause(definition) == " ON sales.orders (user_id)"


def test_extract_on_clause_falls_back():
    assert _extract_on_clause("SOME DEFINITION") == "SOME DEFINITION"


# ---------------------------------------------------------------------------
# _suggest_index_ddl
# ---------------------------------------------------------------------------

def test_suggest_index_ddl_orders_by_selectivity():
    table = _make_table("public", "orders")
    col_low_sel = _make_column(1, "status")    # low cardinality (many dupes)
    col_high_sel = _make_column(2, "user_id")  # high cardinality (mostly unique)
    col_metrics = {
        1: _make_column_metric(1, n_distinct=3.0, null_fraction=0.0),    # 3 distinct values
        2: _make_column_metric(2, n_distinct=-0.98, null_fraction=0.0),  # ~98% unique
    }
    ddl = _suggest_index_ddl(table, [col_low_sel, col_high_sel], col_metrics, n_live_tup=100_000)
    # user_id should come first (most selective)
    assert ddl.startswith("CREATE INDEX CONCURRENTLY ON public.orders (user_id")
    assert "status" in ddl
    assert ddl.endswith(";")


def test_suggest_index_ddl_no_metrics():
    """Without metrics, falls back to input order."""
    table = _make_table("public", "users")
    col_a = _make_column(1, "email")
    col_b = _make_column(2, "age")
    ddl = _suggest_index_ddl(table, [col_a, col_b], {}, n_live_tup=None)
    assert "CREATE INDEX CONCURRENTLY ON public.users" in ddl
    assert "email" in ddl
    assert "age" in ddl


# ---------------------------------------------------------------------------
# _regression_findings
# ---------------------------------------------------------------------------

def test_regression_finding_fires_when_3x_slower():
    history = [100.0] * 10  # consistent 100 ms baseline
    ctx = _base_context(duration_history_ms=history, current_duration_ms=500.0)
    findings = _regression_findings(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.type == "query_regression"
    assert f.severity == "warning"
    assert f.evidence["regression_factor"] == pytest.approx(5.0)
    assert "query_regression" in f.type


def test_regression_finding_critical_at_10x():
    history = [50.0] * 10
    ctx = _base_context(duration_history_ms=history, current_duration_ms=600.0)  # 12x
    findings = _regression_findings(ctx)
    assert findings[0].severity == "critical"


def test_regression_finding_does_not_fire_when_fast():
    history = [100.0] * 10
    ctx = _base_context(duration_history_ms=history, current_duration_ms=150.0)  # 1.5x — below threshold
    assert _regression_findings(ctx) == []


def test_regression_finding_requires_minimum_samples():
    history = [100.0] * 4  # only 4 samples, minimum is 5
    ctx = _base_context(duration_history_ms=history, current_duration_ms=1000.0)
    assert _regression_findings(ctx) == []


def test_regression_finding_skips_when_no_duration():
    ctx = _base_context(duration_history_ms=[100.0] * 10, current_duration_ms=None)
    assert _regression_findings(ctx) == []


# ---------------------------------------------------------------------------
# _schema_change_findings
# ---------------------------------------------------------------------------

def _make_drop(table_id: int, hours_ago: float, name: str = "idx_orders_user") -> DroppedIndexInfo:
    return DroppedIndexInfo(
        name=name,
        definition=f"CREATE INDEX {name} ON public.orders (user_id)",
        table_id=table_id,
        changed_at=_now() - timedelta(hours=hours_ago),
    )


def _make_table_insight(table_id: int) -> SimpleNamespace:
    table = SimpleNamespace(id=table_id, schema_name="public", name="orders")
    return SimpleNamespace(table=table, metric=None, condition_columns=[], index_columns={}, index_names={}, column_metrics={})


def test_schema_change_finding_fires_for_relevant_drop():
    drop = _make_drop(table_id=42, hours_ago=6)
    ctx = _base_context(
        dropped_indexes=[drop],
        tables=[_make_table_insight(table_id=42)],
    )
    findings = _schema_change_findings(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.type == "schema_change_correlation"
    assert f.severity == "warning"
    assert len(f.evidence["dropped_indexes"]) == 1
    assert "idx_orders_user" in f.evidence["dropped_indexes"][0]["name"]


def test_schema_change_finding_critical_with_regression():
    """When query has both a regression AND a dropped index → critical."""
    history = [50.0] * 10
    drop = _make_drop(table_id=42, hours_ago=3)
    ctx = _base_context(
        duration_history_ms=history,
        current_duration_ms=600.0,  # 12x → above regression threshold
        dropped_indexes=[drop],
        tables=[_make_table_insight(table_id=42)],
    )
    findings = _schema_change_findings(ctx)
    assert findings[0].severity == "critical"
    assert findings[0].evidence["correlated_with_regression"] is True


def test_schema_change_finding_does_not_fire_for_unrelated_tables():
    drop = _make_drop(table_id=99, hours_ago=3)  # different table
    ctx = _base_context(
        dropped_indexes=[drop],
        tables=[_make_table_insight(table_id=42)],  # query touches table 42
    )
    assert _schema_change_findings(ctx) == []


def test_schema_change_finding_empty_when_no_drops():
    ctx = _base_context(dropped_indexes=[], tables=[_make_table_insight(42)])
    assert _schema_change_findings(ctx) == []


# ---------------------------------------------------------------------------
# _summary
# ---------------------------------------------------------------------------

def _make_finding(severity: str, confidence: float, title: str = "Test finding") -> FindingDraft:
    return FindingDraft(
        type="test",
        severity=severity,
        confidence=confidence,
        title=title,
        explanation="Test",
        recommendation=None,
        evidence={},
    )


def test_summary_empty_findings():
    assert "No significant issues" in _summary([])


def test_summary_single_finding():
    findings = [_make_finding("warning", 0.7, "High CPU")]
    result = _summary(findings)
    assert "High CPU" in result
    assert "Primary hypothesis" in result


def test_summary_multiple_findings_includes_counts():
    findings = [
        _make_finding("critical", 0.9, "Lock contention"),
        _make_finding("warning", 0.7, "Missing index"),
        _make_finding("warning", 0.65, "Stale stats"),
    ]
    result = _summary(findings)
    assert "Lock contention" in result  # top finding
    assert "1 critical" in result
    assert "2 warning" in result


# ---------------------------------------------------------------------------
# _analyze_context integration smoke test
# ---------------------------------------------------------------------------

def test_analyze_context_returns_sorted_by_confidence():
    """Ensure _analyze_context runs without error on a minimal context and sorts output."""
    ctx = _base_context(
        duration_history_ms=[100.0] * 10,
        current_duration_ms=1500.0,  # triggers regression finding
    )
    findings = _analyze_context(ctx)
    # If there are findings, they must be sorted descending by confidence
    confidences = [f.confidence for f in findings]
    assert confidences == sorted(confidences, reverse=True)
