"""Aggregate statement counters without returning raw snapshots to the API."""

from datetime import datetime

from sqlalchemy import (
    Integer, Row, and_, case, cast, func, literal,
    null, select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import CompoundSelect, Join, Select, Subquery
from sqlalchemy.sql.selectable import CTE

from database.models.metric.query_workload import QueryWorkloadMetric as Workload, StatementText


def build_intervals(
    database_id: int, start_at: datetime, end_at: datetime,
) -> Select:
    """Window only counters and the reset marker needed to validate deltas."""
    fields = {
        name: getattr(Workload, name)
        for name in (
            "collected_at", "query_id", "user_id", "is_toplevel", "calls",
            "total_exec_time", "shared_blks_read", "shared_blks_hit",
            "stats_reset", "dealloc", "user_name", "stats_since",
        )
    }
    fields["has_query"] = Workload.statement_text_id.in_(select(StatementText.id).where(
        func.octet_length(StatementText.query) > 0,
    ))
    # Collectors hash the exact SQL text. Keep large SQL outside the window and
    # fetch a representative only after aggregating its compact hash identity.
    fields["text_key"] = Workload.statement_text_id
    # PostgreSQL otherwise carries the original JSON and SQL through the window.
    # A narrow materialized input bounds its sort and partition storage.
    source = select(*[value.label(name) for name, value in fields.items()]).where(
        Workload.database_id == database_id,
        Workload.collected_at >= start_at, Workload.collected_at <= end_at,
        Workload.is_toplevel.is_(True),
    ).cte("statement_input").prefix_with("MATERIALIZED")
    fields = dict(source.c.items())
    previous = {
        "prev_" + name: func.lag(fields[name], type_=fields[name].type).over(
            partition_by=(source.c.query_id, source.c.user_id, source.c.is_toplevel),
            order_by=source.c.collected_at,
        )
        for name in (
            "collected_at", "calls", "total_exec_time", "shared_blks_read",
            "shared_blks_hit", "stats_reset", "dealloc", "stats_since",
        )
    }
    return select(*[value.label(name) for name, value in (fields | previous).items()])


def _join_texts(delta: Subquery | CTE, database_id: int) -> Join:
    return delta.join(StatementText, and_(
        StatementText.database_id == database_id, StatementText.id == delta.c.text_key,
    ))


def _deltas(database_id: int, start_at: datetime, end_at: datetime) -> Subquery:
    sampled = build_intervals(database_id, start_at, end_at).subquery()
    row = sampled.c
    valid = and_(
        row.prev_collected_at.is_not(None),
        *[row[name].is_not_distinct_from(row["prev_" + name])
          for name in ("stats_reset", "dealloc", "stats_since")],
        *[row[name] >= row["prev_" + name]
          for name in ("calls", "total_exec_time", "shared_blks_read", "shared_blks_hit")],
    )
    return select(
        sampled,
        valid.label("delta_valid"),
        case((valid, row.calls - row.prev_calls), else_=0).label("calls_delta"),
        case((valid, row.total_exec_time - row.prev_total_exec_time), else_=0).label("duration_delta"),
        case((valid, row.prev_collected_at), else_=row.collected_at).label("first_seen"),
    ).subquery()


def build_statement_summary(
    database_id: int, start_at: datetime, end_at: datetime, user_name: str | None,
    intervals: Subquery | CTE | None = None,
) -> Select:
    """Return one summary per SQL text, identity and user, including gaps."""
    if intervals is None:
        intervals = _deltas(database_id, start_at, end_at)
    delta = intervals.c
    statement = select(
        delta.query_id, delta.user_id, literal(True).label("is_toplevel"),
        func.min(delta.collected_at).label("collected_at"),
        delta.user_name, func.sum(delta.calls_delta).label("execution_count"),
        func.sum(delta.calls_delta).label("duration_count"),
        func.sum(delta.duration_delta).label("duration_sum"),
        func.max(cast(delta.delta_valid, Integer)).label("delta_valid"),
        func.min(delta.first_seen).label("first_seen"),
        func.max(delta.collected_at).label("last_seen"),
        delta.text_key,
    ).where(delta.has_query)
    if user_name is not None:
        statement = statement.where(delta.user_name == user_name)
    totals = statement.group_by(
        delta.query_id, delta.user_id, delta.text_key, delta.user_name,
    ).subquery()
    row = totals.c
    return select(
        row.query_id.label("pg_query_id"), StatementText.query_hash, StatementText.query,
        row.user_name, row.execution_count, row.duration_count,
        row.duration_sum, row.delta_valid, row.first_seen, row.last_seen, row.text_key,
    ).select_from(_join_texts(totals, database_id)).order_by(row.first_seen)


def build_statement_timeline(
    database_id: int, start_at: datetime, end_at: datetime,
    user_name: str | None, text_keys: list[int] | None,
    intervals: Subquery | CTE | None = None,
) -> Select:
    """Aggregate actual collection intervals before transferring timeline data."""
    if intervals is None:
        intervals = _deltas(database_id, start_at, end_at)
    delta = intervals.c
    statement = select(
        delta.prev_collected_at.label("interval_start"),
        delta.collected_at.label("timestamp"),
        func.sum(delta.calls_delta).label("execution_count"),
        func.sum(delta.duration_delta).label("duration_sum"),
    ).where(delta.delta_valid, delta.has_query)
    if user_name is not None:
        statement = statement.where(delta.user_name == user_name)
    if text_keys is not None:
        statement = statement.where(delta.text_key.in_(text_keys))
    return statement.group_by(delta.prev_collected_at, delta.collected_at).order_by(
        delta.collected_at, delta.prev_collected_at,
    )


def build_statement_bundle(
    database_id: int, start_at: datetime, end_at: datetime, user_name: str | None,
) -> CompoundSelect:
    """Evaluate deltas once for unfiltered summaries and collection intervals."""
    intervals = select(_deltas(database_id, start_at, end_at)).cte(
        "statement_deltas",
    ).prefix_with("MATERIALIZED")
    summary = build_statement_summary(database_id, start_at, end_at, user_name, intervals).subquery()
    timeline = build_statement_timeline(database_id, start_at, end_at, user_name, None, intervals).subquery()
    return select(literal("summary").label("kind"), summary).union_all(select(
        literal("timeline"), null(), null(), null(), null(),
        timeline.c.execution_count, timeline.c.execution_count,
        timeline.c.duration_sum, literal(1),
        timeline.c.interval_start, timeline.c.timestamp, null(),
    ))


async def fetch_compact_statements(
    db: AsyncSession, database_id: int, start_at: datetime, end_at: datetime,
    user_name: str | None,
) -> list[Row]:
    """Fetch summaries instead of full, JSON-bearing statement snapshots."""
    return list((await db.execute(
        build_statement_summary(database_id, start_at, end_at, user_name),
    )).all())
