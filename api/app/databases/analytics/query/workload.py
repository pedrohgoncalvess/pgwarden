"""Statement snapshots and reset-safe deltas; never manufacture executions."""

import json
from types import SimpleNamespace

from sqlalchemy import func, select

from database.models.metric.query_workload import QueryWorkloadMetric as Workload


def payload(value: str | None) -> dict:
    if not value:
        return {}
    try:
        result = json.loads(value)
        if not isinstance(result, dict):
            return {}
        if result.get("queryid") is not None:
            result["queryid"] = str(result["queryid"])
        return result
    except (ValueError, TypeError):
        return {}


def valid_delta(row) -> bool:
    if row.previous_at is None or row.stats_reset != row.prev_stats_reset or row.dealloc != row.prev_dealloc:
        return False
    # Newer PostgreSQL versions also expose per-entry resets. Global reset and
    # monotonic counters alone cannot detect a reset followed by a busy query.
    if payload(row.statement_data).get("stats_since") != payload(row.prev_statement_data).get("stats_since"):
        return False
    return all(getattr(row, name) >= getattr(row, "prev_" + name)
               for name in ("calls", "total_exec_time", "shared_blks_read", "shared_blks_hit"))


async def snapshots(db, database_id, start_at, end_at, pg_query_id=None, query_hash=None, limit=None):
    columns = [Workload]
    for name in ("calls", "total_exec_time", "shared_blks_read", "shared_blks_hit", "stats_reset", "dealloc", "statement_data"):
        column = getattr(Workload, name)
        columns.append(func.lag(column, type_=column.type).over(
            partition_by=(Workload.query_id, Workload.user_id, Workload.is_toplevel),
            order_by=Workload.collected_at,
        ).label("prev_" + name))
    columns.append(func.lag(Workload.collected_at, type_=Workload.collected_at.type).over(
        partition_by=(Workload.query_id, Workload.user_id, Workload.is_toplevel),
        order_by=Workload.collected_at,
    ).label("previous_at"))
    # Intervals crossing the requested start are deliberately excluded, so the
    # window can be bounded before lag rather than scanning all retained data.
    statement = select(*columns).where(
        Workload.database_id == database_id, Workload.collected_at >= start_at,
        Workload.collected_at <= end_at,
    )
    if pg_query_id is not None:
        statement = statement.where(Workload.query_id == pg_query_id)
    sampled = statement.subquery()
    statement = select(sampled).where(sampled.c.collected_at >= start_at)
    if query_hash is not None and pg_query_id is None:
        identities = select(Workload.query_id).where(
            Workload.database_id == database_id, Workload.query_hash == query_hash,
        )
        statement = statement.where(sampled.c.query_id.in_(identities))
    if limit is not None:
        rows = (await db.execute(statement.order_by(sampled.c.collected_at.desc()).limit(limit))).all()
        return list(reversed(rows))
    return (await db.execute(statement.order_by(sampled.c.collected_at))).all()


async def fetch_statement_groups(db, database_id, start_at, end_at, user_name=None):
    rows = await snapshots(db, database_id, start_at, end_at)
    groups = []
    for row in rows:
        if not row.is_toplevel or not row.query or (user_name is not None and row.user_name != user_name):
            continue
        valid = valid_delta(row) and row.previous_at >= start_at
        calls = row.calls - row.prev_calls if valid else 0
        duration = row.total_exec_time - row.prev_total_exec_time if valid else 0
        groups.append(SimpleNamespace(
            pg_query_id=row.query_id, query_hash=row.query_hash, query=row.query,
            user_name=row.user_name, application_name=None, source="statements",
            delta_valid=valid, execution_count=calls, duration_count=calls,
            duration_sum=duration, duration_min=None, duration_max=None,
            first_seen=row.previous_at if valid else row.collected_at,
            last_seen=row.collected_at, bucket=None,
        ))
    return groups
