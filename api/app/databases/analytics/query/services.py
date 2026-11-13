import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.analytics.query.sources import fetch_analytics
from app.databases.analytics.query.context_tables import get_context_tables
from app.databases.analytics.query.models import (
    QueryAnalyticsResponse,
    QueryContextDatabaseConnections,
    QueryContextExecution,
    QueryContextLock,
    QueryContextResponse,
    QueryContextServerMetrics,
    QueryExecutionHistoryItem,
    QueryExecutionHistoryResponse,
)
from app.databases.analytics.query.workload import snapshots, valid_delta
from app.databases.analytics.query.statement_statistics import get_statistics
from app.databases.schemas.exceptions import DatabaseNotFoundError
from database.models.analytics.query import Query
from database.models.metadata.database import Database
from database.models.metadata.table import Table
from database.models.metric.cpu import CpuMetric
from database.models.metric.disk import DiskMetric
from database.models.metric.io import IoMetric
from database.models.metric.lock import LockMetric
from database.models.metric.native_query import NativeQueryMetric
from database.models.metric.query_workload import QueryWorkloadMetric
from database.models.metric.ram import RamMetric
from database.models.metric.session import SessionMetric
from utils import decrypt_or_plain

PRESET_RANGES = {
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
    "2w": timedelta(weeks=2),
    "1m": timedelta(days=30),
}

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", flags=re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_DOUBLE_QUOTE_RE = re.compile(r'"([^"]+)"')
_STRING_LITERAL_RE = re.compile(r"'(?:''|[^'])*'")
_NUMERIC_LITERAL_RE = re.compile(r"(?<![\w.])-?\d+(\.\d+)?(?![\w.])")
_IN_CLAUSE_RE = re.compile(r"\bin\s*\(\s*(\?\s*,\s*)*\?\s*\)", flags=re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _resolve_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    preset: Optional[str],
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    end_dt = _parse_iso_datetime(end_date) or now

    if start_date:
        start_dt = _parse_iso_datetime(start_date) or (now - timedelta(days=7))
    elif preset and preset in PRESET_RANGES:
        start_dt = end_dt - PRESET_RANGES[preset]
    else:
        start_dt = end_dt - timedelta(days=7)

    return start_dt, end_dt


def _remove_sql_comments(query: str) -> str:
    query = _BLOCK_COMMENT_RE.sub(" ", query)
    query = _LINE_COMMENT_RE.sub(" ", query)
    return query


def _normalize_query(query: Optional[str]) -> str:
    if not query:
        return ""

    query = _remove_sql_comments(query)
    query = _DOUBLE_QUOTE_RE.sub(r"\1", query)
    query = query.lower()
    query = _STRING_LITERAL_RE.sub("?", query)
    query = re.sub(r"\$\d+\b", "?", query)
    query = _NUMERIC_LITERAL_RE.sub("?", query)
    query = _IN_CLAUSE_RE.sub("in (?)", query)
    query = _WHITESPACE_RE.sub(" ", query).strip()

    if query.endswith(";"):
        query = query[:-1].strip()

    return query


def _build_preview(query_signature: str, max_length: int = 120) -> str:
    if len(query_signature) <= max_length:
        return query_signature
    return query_signature[:max_length].rstrip() + "..."


def _normalize_search_terms(search: Optional[List[str]]) -> list[str]:
    terms: list[str] = []
    for value in search or []:
        terms.extend(term.strip().lower() for term in value.split(","))
    return [term for term in terms if term]


async def get_query_analytics(
    db: AsyncSession,
    database_id: UUID,
    start_date: Optional[str],
    end_date: Optional[str],
    preset: Optional[str],
    user_name: Optional[str],
    application_name: Optional[str],
    state: Optional[str],
    search: Optional[List[str]],
    exclude: Optional[List[str]],
    limit: Optional[int] = 50,
    order_by: str = "executions",
    order_dir: str = "desc",
) -> QueryAnalyticsResponse:
    db_result = await db.execute(
        select(Database).where(
            Database.public_id == database_id,
            Database.deleted_at.is_(None),
        )
    )
    database = db_result.scalar_one_or_none()
    if not database:
        raise DatabaseNotFoundError(str(database_id))

    start_dt, end_dt = _resolve_date_range(start_date, end_date, preset)

    items, timeline, total, filters = await fetch_analytics(
        db, database.id, start_dt, end_dt, user_name, application_name, state,
        _normalize_query, _normalize_search_terms(search),
        [term.strip().lower() for term in (exclude or []) if term.strip()],
        limit, order_by, order_dir,
    )
    return QueryAnalyticsResponse(
        database_id=database_id,
        database_name=decrypt_or_plain(database.db_name),
        start_at=start_dt, end_at=end_dt, items=items,
        total=total, timeline=timeline, filters=filters,
    )


async def get_query_execution_history(
    db: AsyncSession,
    database_id: UUID,
    query_hash: str,
    start_date: Optional[str],
    end_date: Optional[str],
    preset: Optional[str],
    limit: int = 500,
) -> QueryExecutionHistoryResponse:
    db_result = await db.execute(
        select(Database).where(
            Database.public_id == database_id,
            Database.deleted_at.is_(None),
        )
    )
    database = db_result.scalar_one_or_none()
    if not database:
        raise DatabaseNotFoundError(str(database_id))

    start_dt, end_dt = _resolve_date_range(start_date, end_date, preset)
    if limit > 2000:
        limit = 2000

    pg_id = await _resolve_pg_id(db, database.id, query_hash)
    identity = (NativeQueryMetric.query_id == pg_id) if pg_id is not None else (NativeQueryMetric.query_hash == query_hash)
    result = await db.execute(
        select(
            NativeQueryMetric.collected_at,
            NativeQueryMetric.query_duration_ms,
            NativeQueryMetric.user_name,
            NativeQueryMetric.application_name,
            NativeQueryMetric.query,
        )
        .where(
            NativeQueryMetric.database_id == database.id,
            identity,
            NativeQueryMetric.collected_at >= start_dt,
            NativeQueryMetric.collected_at <= end_dt,
        )
        .order_by(NativeQueryMetric.collected_at.desc())
        .limit(limit)
    )
    rows = result.all()

    query_text = rows[0].query if rows else ""
    query_preview = _build_preview(_normalize_query(query_text))

    items = [
        QueryExecutionHistoryItem(
            collected_at=row.collected_at,
            duration_ms=row.query_duration_ms,
            user_name=row.user_name,
            application_name=row.application_name,
            rows_returned=None,
        )
        for row in reversed(rows)  # Oldest first for charts
    ]

    statement_rows = await snapshots(db, database.id, start_dt, end_dt, pg_id, query_hash, limit=limit)
    for row in statement_rows:
        valid = valid_delta(row) and row.previous_at >= start_dt
        calls = row.calls - row.prev_calls if valid else None
        duration = row.total_exec_time - row.prev_total_exec_time if valid else None
        items.append(QueryExecutionHistoryItem(
            collected_at=row.collected_at, duration_ms=duration / calls if calls else None,
            user_name=row.user_name, application_name=None, rows_returned=None,
            source="statements", calls=row.calls, calls_delta=calls,
            total_exec_time_delta_ms=duration, user_id=row.user_id,
            is_toplevel=row.is_toplevel, statement_data=get_statistics(row),
        ))
    items.sort(key=lambda item: item.collected_at)
    items = items[-limit:]
    if not query_preview and statement_rows:
        query_preview = _build_preview(_normalize_query(statement_rows[-1].query))
    return QueryExecutionHistoryResponse(
        query_hash=query_hash,
        query_preview=query_preview,
        items=items,
    )


async def get_query_context(
    db: AsyncSession,
    database_id: UUID,
    query_hash: str,
    collected_at: datetime,
    source: str | None = None,
    user_id: int | None = None,
    is_toplevel: bool | None = None,
) -> QueryContextResponse:
    db_result = await db.execute(
        select(Database).where(
            Database.public_id == database_id,
            Database.deleted_at.is_(None),
        )
    )
    database = db_result.scalar_one_or_none()
    if not database:
        raise DatabaseNotFoundError(str(database_id))

    pg_id = await _resolve_pg_id(db, database.id, query_hash)
    if source == "statements":
        return await _statement_context(db, database, query_hash, pg_id, collected_at, user_id, is_toplevel)
    identity = (NativeQueryMetric.query_id == pg_id) if pg_id is not None else (NativeQueryMetric.query_hash == query_hash)
    # 1. Fetch the exact execution
    exec_result = await db.execute(
        select(NativeQueryMetric)
        .where(
            NativeQueryMetric.database_id == database.id,
            identity,
            NativeQueryMetric.collected_at == collected_at,
        )
        .limit(1)
    )
    execution_row = exec_result.scalar_one_or_none()
    if not execution_row:
        if source == "activity":
            raise ValueError("Execution not found")
        return await _statement_context(db, database, query_hash, pg_id, collected_at)

    execution = QueryContextExecution(
        collected_at=execution_row.collected_at,
        duration_ms=execution_row.query_duration_ms,
        query=execution_row.query or "",
        user_name=execution_row.user_name,
        application_name=execution_row.application_name,
    )

    window_start = collected_at - timedelta(seconds=45)
    window_end = collected_at + timedelta(seconds=45)

    # 2. Server Metrics (fetch closest/most recent metric for each type and check staleness)
    cpu_query = await db.execute(
        select(CpuMetric)
        .where(CpuMetric.server_id == database.server_id, CpuMetric.collected_at <= window_end)
        .order_by(CpuMetric.collected_at.desc())
        .limit(1)
    )
    ram_query = await db.execute(
        select(RamMetric)
        .where(RamMetric.server_id == database.server_id, RamMetric.collected_at <= window_end)
        .order_by(RamMetric.collected_at.desc())
        .limit(1)
    )
    disk_query = await db.execute(
        select(DiskMetric)
        .where(DiskMetric.server_id == database.server_id, DiskMetric.collected_at <= window_end)
        .order_by(DiskMetric.collected_at.desc())
        .limit(10)
    )
    io_query = await db.execute(
        select(IoMetric)
        .where(IoMetric.server_id == database.server_id, IoMetric.collected_at <= window_end)
        .order_by(IoMetric.collected_at.desc())
        .limit(1)
    )
    
    cpu_row = cpu_query.scalar_one_or_none()
    ram_row = ram_query.scalar_one_or_none()
    disk_rows = disk_query.scalars().all()
    io_row = io_query.scalar_one_or_none()

    # Disk metric calculation: pick root '/' or max mount point percent
    disk_percent = None
    disk_row = None
    if disk_rows:
        root_disk = next((d for d in disk_rows if d.mount_point in ["/", "C:", "C:\\"]), None)
        disk_row = root_disk or max(disk_rows, key=lambda d: d.percent if d.percent is not None else -1)
        disk_percent = disk_row.percent if disk_row else None

    STALE_THRESHOLD_SECONDS = 180  # 3 minutes

    def is_stale(metric_time: Optional[datetime]) -> bool:
        if not metric_time:
            return True
        return abs((collected_at - metric_time).total_seconds()) > STALE_THRESHOLD_SECONDS

    server_metrics = QueryContextServerMetrics(
        cpu_percent=cpu_row.cpu_percent if cpu_row else None,
        ram_percent=ram_row.percent if ram_row else None,
        disk_percent=disk_percent,
        read_bytes=io_row.read_bytes if io_row else None,
        write_bytes=io_row.write_bytes if io_row else None,
        cpu_stale=is_stale(cpu_row.collected_at) if cpu_row else True,
        ram_stale=is_stale(ram_row.collected_at) if ram_row else True,
        disk_stale=is_stale(disk_row.collected_at) if disk_row else True,
        io_stale=is_stale(io_row.collected_at) if io_row else True,
    )

    # 3. Connections
    state_counts = {"active": 0, "idle": 0, "idle in transaction": 0, "waiting": 0}
    latest_session_time_result = await db.execute(
        select(SessionMetric.collected_at)
        .where(SessionMetric.database_id == database.id, SessionMetric.collected_at >= window_start, SessionMetric.collected_at <= window_end)
        .order_by(SessionMetric.collected_at.desc())
        .limit(1)
    )
    latest_session_time = latest_session_time_result.scalar_one_or_none()
    if latest_session_time:
        latest_sessions = await db.execute(
            select(SessionMetric.state, SessionMetric.wait_event_type)
            .where(SessionMetric.database_id == database.id, SessionMetric.collected_at == latest_session_time)
        )
        for s in latest_sessions.all():
            state = s.state or ""
            if state.startswith("active"):
                if s.wait_event_type == "Lock":
                    state_counts["waiting"] += 1
                else:
                    state_counts["active"] += 1
            elif state.startswith("idle in transaction"):
                state_counts["idle in transaction"] += 1
            elif state.startswith("idle"):
                state_counts["idle"] += 1

    database_connections = QueryContextDatabaseConnections(
        active=state_counts["active"],
        idle=state_counts["idle"],
        idle_in_transaction=state_counts["idle in transaction"],
        waiting=state_counts["waiting"],
    )

    # 4. Tables
    # Find table hits for this query hash from Query analytics model
    query_row_result = await db.execute(
        select(Query.id)
        .where(
            Query.database_id == database.id,
            (Query.pg_query_id == pg_id) if pg_id is not None else (func.lower(Query.hash) == query_hash.lower()),
        )
        .limit(1)
    )
    query_id = query_row_result.scalar_one_or_none()
    
    tables_response = (
        await get_context_tables(db, database.id, query_id, window_end)
        if query_id else []
    )

    # 5. Locks (filtered to tables accessed by query or execution PID)
    locks_response = []
    related_table_ids = [t.table_id for t in tables_response]
    
    lock_conditions = [
        LockMetric.database_id == database.id,
        LockMetric.collected_at >= window_start,
        LockMetric.collected_at <= window_end,
    ]
    
    if related_table_ids:
        lock_conditions.append(
            or_(
                LockMetric.table_id.in_(related_table_ids),
                LockMetric.holder_pid == execution_row.pid,
            )
        )
    elif execution_row.pid:
        lock_conditions.append(LockMetric.holder_pid == execution_row.pid)

    locks_result = await db.execute(
        select(LockMetric, Table.name.label("table_name"))
        .outerjoin(Table, Table.id == LockMetric.table_id)
        .where(*lock_conditions)
        .order_by(LockMetric.collected_at.desc())
        .limit(100)
    )
    seen_locks = set()
    for lock_row, t_name in locks_result.all():
        key = (lock_row.holder_pid, lock_row.type, lock_row.mode, t_name, lock_row.is_granted)
        if key in seen_locks:
            continue
        seen_locks.add(key)
        locks_response.append(
            QueryContextLock(
                table_name=t_name,
                holder_pid=lock_row.holder_pid,
                type=lock_row.type,
                mode=lock_row.mode,
                is_granted=lock_row.is_granted,
                query_preview=lock_row.query_preview,
            )
        )

    return QueryContextResponse(
        execution=execution,
        server_metrics=server_metrics,
        database_connections=database_connections,
        tables=tables_response,
        locks=locks_response,
    )


async def _resolve_pg_id(db: AsyncSession, database_id: int, query_hash: str) -> int | None:
    if query_hash.startswith("pg:"):
        try:
            value = int(query_hash[3:])
            if value and -(2**63) <= value < 2**63:
                return value
        except ValueError:
            pass
        raise ValueError("Invalid PostgreSQL query identity")
    for model, hash_column, id_column in (
        (Query, Query.hash, Query.pg_query_id),
        (NativeQueryMetric, NativeQueryMetric.query_hash, NativeQueryMetric.query_id),
        (QueryWorkloadMetric, QueryWorkloadMetric.query_hash, QueryWorkloadMetric.query_id),
    ):
        result = await db.execute(select(id_column).where(
            model.database_id == database_id, hash_column == query_hash,
            id_column.is_not(None), id_column != 0,
        ).distinct().limit(2))
        ids = result.scalars().all()
        if len(ids) == 1:
            return ids[0]
        if len(ids) > 1:
            return None
    return None


async def _statement_context(db, database, query_hash, pg_id, collected_at, user_id=None, is_toplevel=None):
    identity = (QueryWorkloadMetric.query_id == pg_id) if pg_id is not None else (QueryWorkloadMetric.query_hash == query_hash)
    statement = select(QueryWorkloadMetric).where(
        QueryWorkloadMetric.database_id == database.id, identity,
        QueryWorkloadMetric.collected_at == collected_at,
    )
    if user_id is not None:
        statement = statement.where(QueryWorkloadMetric.user_id == user_id)
    if is_toplevel is not None:
        statement = statement.where(QueryWorkloadMetric.is_toplevel == is_toplevel)
    result = await db.execute(statement.order_by(QueryWorkloadMetric.user_id, QueryWorkloadMetric.is_toplevel.desc()).limit(1))
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise ValueError("Execution not found")
    result = await db.execute(select(Query.id).where(
        Query.database_id == database.id,
        (Query.pg_query_id == pg_id) if pg_id is not None else (Query.hash == query_hash),
    ).order_by(Query.id).limit(1))
    query_id = result.scalar_one_or_none()
    return QueryContextResponse(
        execution=QueryContextExecution(
            collected_at=collected_at, duration_ms=None, query=snapshot.query or "",
            user_name=snapshot.user_name, application_name=None, source="statements",
            statement_data=get_statistics(snapshot),
        ),
        server_metrics=QueryContextServerMetrics(
            cpu_percent=None, ram_percent=None, disk_percent=None,
            read_bytes=None, write_bytes=None,
            cpu_stale=True, ram_stale=True, disk_stale=True, io_stale=True,
        ),
        database_connections=QueryContextDatabaseConnections(active=None, idle=None, idle_in_transaction=None, waiting=None),
        tables=await get_context_tables(db, database.id, query_id, collected_at) if query_id else [],
        locks=[],
    )
