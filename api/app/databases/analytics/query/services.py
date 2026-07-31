import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, and_, tuple_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.analytics.query.models import (
    QueryAnalyticsResponse,
    QueryAnalyticsItem,
    QueryAnalyticsTimelinePoint,
    QueryAnalyticsFilters,
    QueryAnalyticsUserBreakdown,
    QueryAnalyticsApplicationBreakdown,
    QueryExecutionHistoryItem,
    QueryExecutionHistoryResponse,
    QueryContextResponse,
    QueryContextExecution,
    QueryContextServerMetrics,
    QueryContextDatabaseConnections,
    QueryContextTable,
    QueryContextIndex,
    QueryContextColumn,
)
from app.databases.schemas.exceptions import DatabaseNotFoundError
from database.models.metadata.database import Database
from database.models.metadata.table import Table
from database.models.metadata.column import ColumnModel
from database.models.metadata.index import Index
from database.models.metadata.index_column import IndexColumn
from database.models.metric.native_query import NativeQueryMetric
from database.models.metric.cpu import CpuMetric
from database.models.metric.ram import RamMetric
from database.models.metric.disk import DiskMetric
from database.models.metric.io import IoMetric
from database.models.metric.session import SessionMetric
from database.models.metric.table import TableMetric
from database.models.metric.column import ColumnMetric
from database.models.metric.index import IndexMetric
from database.models.metric.lock import LockMetric
from app.databases.analytics.query.models import (
    QueryAnalyticsResponse,
    QueryExecutionHistoryResponse,
    QueryContextResponse,
    QueryExecutionHistoryItem,
    QueryContextExecution,
    QueryContextServerMetrics,
    QueryContextDatabaseConnections,
    QueryContextTable,
    QueryContextIndex,
    QueryContextColumn,
    QueryContextLock,
)
from database.models.analytics.query_table_hit import QueryTableHit
from database.models.analytics.query import Query
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


def _bucket_timestamp(ts: datetime, bucket_minutes: int = 5) -> datetime:
    return ts.replace(
        minute=(ts.minute // bucket_minutes) * bucket_minutes,
        second=0,
        microsecond=0,
    )


def _avg_duration(durations: list[Optional[float]]) -> Optional[float]:
    total = 0.0
    count = 0
    for d in durations:
        if d is not None:
            total += d
            count += 1
    if count == 0:
        return None
    return total / count


def _sort_key(item: tuple, order_by: str) -> float:
    """Compute a numeric sort key for a (signature, agg) pair."""
    agg = item[1]
    if order_by == "executions":
        return agg["execution_count"]
    durations = agg["durations"]
    valid = [d for d in durations if d is not None]
    if not valid:
        return 0.0
    if order_by == "max_duration":
        return max(valid)
    if order_by == "total_duration":
        return sum(valid)
    return sum(valid) / len(valid)


async def _fetch_batch(
    db: AsyncSession,
    database_id: int,
    start_dt: datetime,
    end_dt: datetime,
    user_name: Optional[str],
    application_name: Optional[str],
    state: Optional[str],
    cursor: Optional[tuple],
    batch_size: int,
):
    filters = [
        NativeQueryMetric.database_id == database_id,
        NativeQueryMetric.collected_at >= start_dt,
        NativeQueryMetric.collected_at <= end_dt,
    ]

    if user_name is not None:
        filters.append(NativeQueryMetric.user_name == user_name)
    if application_name is not None:
        filters.append(NativeQueryMetric.application_name == application_name)
    if state is not None:
        filters.append(NativeQueryMetric.state == state)

    if cursor:
        filters.append(
            tuple_(
                NativeQueryMetric.collected_at,
                NativeQueryMetric.pid,
                NativeQueryMetric.backend_start,
            ) > cursor
        )

    return await db.execute(
        select(
            NativeQueryMetric.collected_at,
            NativeQueryMetric.pid,
            NativeQueryMetric.backend_start,
            NativeQueryMetric.query_start,
            NativeQueryMetric.user_name,
            NativeQueryMetric.application_name,
            NativeQueryMetric.state,
            NativeQueryMetric.query,
            NativeQueryMetric.query_hash,
            NativeQueryMetric.query_duration_ms,
        )
        .where(and_(*filters))
        .order_by(
            NativeQueryMetric.collected_at,
            NativeQueryMetric.pid,
            NativeQueryMetric.backend_start,
        )
        .limit(batch_size)
    )


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

    search_terms = _normalize_search_terms(search)
    exclude_terms = [term.strip().lower() for term in (exclude or []) if term.strip()]

    BATCH_SIZE = 50_000
    MAX_TOTAL_ROWS = 500_000

    executions: dict[tuple, dict] = {}
    users_set: set[Optional[str]] = set()
    applications_set: set[Optional[str]] = set()
    states_set: set[Optional[str]] = set()
    signature_cache: dict[Optional[str], str] = {}
    total_rows = 0
    truncated = False
    cursor: Optional[tuple] = None

    while total_rows < MAX_TOTAL_ROWS:
        rows_result = await _fetch_batch(
            db, database.id, start_dt, end_dt, user_name, application_name,
            state, cursor, BATCH_SIZE,
        )
        rows = rows_result.all()
        if not rows:
            break

        total_rows += len(rows)
        if total_rows >= MAX_TOTAL_ROWS:
            truncated = True

        for row in rows:
            users_set.add(row.user_name)
            applications_set.add(row.application_name)
            states_set.add(row.state)

            query_hash = row.query_hash
            signature = signature_cache.get(query_hash)
            if signature is None:
                query_text = row.query or ""
                signature = _normalize_query(query_text)
                signature_cache[query_hash] = signature

            if not signature:
                continue

            if search_terms and not any(term in signature for term in search_terms):
                continue

            if exclude_terms and any(term in signature for term in exclude_terms):
                continue

            exec_key = (row.pid, row.backend_start, row.query_start or row.collected_at, query_hash)
            existing = executions.get(exec_key)
            if existing is None or row.collected_at < existing["first_seen"]:
                executions[exec_key] = {
                    "signature": signature,
                    "query_hash": query_hash,
                    "query": row.query or "",
                    "user_name": row.user_name,
                    "application_name": row.application_name,
                    "state": row.state,
                    "first_seen": row.collected_at,
                    "last_seen": row.collected_at,
                    "durations": [],
                }
            executions[exec_key]["durations"].append(row.query_duration_ms)
            if row.collected_at > executions[exec_key]["last_seen"]:
                executions[exec_key]["last_seen"] = row.collected_at

        last_row = rows[-1]
        cursor = (last_row.collected_at, last_row.pid, last_row.backend_start)

        if len(rows) < BATCH_SIZE:
            break

    signatures: dict[str, dict] = defaultdict(
        lambda: {
            "query_preview": "",
            "query_hash": None,
            "execution_count": 0,
            "durations": [],
            "users": defaultdict(int),
            "applications": defaultdict(int),
            "first_seen": None,
            "last_seen": None,
        }
    )

    timeline_buckets: dict[datetime, list] = defaultdict(list)

    for exec_data in executions.values():
        signature = exec_data["signature"]
        agg = signatures[signature]
        if agg["execution_count"] == 0:
            agg["query_preview"] = _build_preview(signature)
            agg["query_hash"] = exec_data["query_hash"]

        exec_avg_duration = _avg_duration(exec_data["durations"])

        agg["execution_count"] += 1
        if exec_avg_duration is not None:
            agg["durations"].append(exec_avg_duration)
        agg["users"][exec_data["user_name"]] += 1
        agg["applications"][exec_data["application_name"]] += 1

        if agg["first_seen"] is None or exec_data["first_seen"] < agg["first_seen"]:
            agg["first_seen"] = exec_data["first_seen"]
        if agg["last_seen"] is None or exec_data["last_seen"] > agg["last_seen"]:
            agg["last_seen"] = exec_data["last_seen"]

        bucket = _bucket_timestamp(exec_data["first_seen"])
        timeline_buckets[bucket].append(exec_avg_duration)

    total = len(signatures)
    sorted_signatures = sorted(
        signatures.items(),
        key=lambda item: (_sort_key(item, order_by), item[0]),
        reverse=order_dir == "desc",
    )
    page_signatures = sorted_signatures[:limit] if limit else sorted_signatures

    items = []
    for signature, agg in page_signatures:
        durations = agg["durations"]
        avg_duration = sum(durations) / len(durations) if durations else None
        max_duration = max(durations) if durations else None
        min_duration = min(durations) if durations else None
        total_duration = sum(durations) if durations else None

        user_breakdown = [
            QueryAnalyticsUserBreakdown(user_name=user, execution_count=count)
            for user, count in sorted(agg["users"].items(), key=lambda x: x[1], reverse=True)
        ]
        application_breakdown = [
            QueryAnalyticsApplicationBreakdown(application_name=app, execution_count=count)
            for app, count in sorted(agg["applications"].items(), key=lambda x: x[1], reverse=True)
        ]

        items.append(
            QueryAnalyticsItem(
                query_signature=signature,
                query_preview=agg["query_preview"],
                query_hash=agg["query_hash"],
                execution_count=agg["execution_count"],
                avg_duration_ms=avg_duration,
                max_duration_ms=max_duration,
                min_duration_ms=min_duration,
                total_duration_ms=total_duration,
                unique_users=len(agg["users"]),
                user_breakdown=user_breakdown,
                unique_applications=len(agg["applications"]),
                application_breakdown=application_breakdown,
                first_seen=agg["first_seen"],
                last_seen=agg["last_seen"],
            )
        )

    timeline = []
    for bucket in sorted(timeline_buckets.keys()):
        bucket_durations = [d for d in timeline_buckets[bucket] if d is not None]
        timeline.append(
            QueryAnalyticsTimelinePoint(
                timestamp=bucket,
                execution_count=len(timeline_buckets[bucket]),
                avg_duration_ms=(sum(bucket_durations) / len(bucket_durations)) if bucket_durations else None,
            )
        )

    return QueryAnalyticsResponse(
        database_id=database_id,
        database_name=decrypt_or_plain(database.db_name),
        start_at=start_dt,
        end_at=end_dt,
        items=items,
        total=total,
        timeline=timeline,
        filters=QueryAnalyticsFilters(
            users=sorted(users_set, key=lambda x: (x is None, x or "")),
            applications=sorted(applications_set, key=lambda x: (x is None, x or "")),
            states=sorted(states_set, key=lambda x: (x is None, x or "")),
        ),
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
            NativeQueryMetric.query_hash == query_hash,
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

    # 1. Fetch the exact execution
    exec_result = await db.execute(
        select(NativeQueryMetric)
        .where(
            NativeQueryMetric.database_id == database.id,
            NativeQueryMetric.query_hash == query_hash,
            NativeQueryMetric.collected_at == collected_at,
        )
        .limit(1)
    )
    execution_row = exec_result.scalar_one_or_none()
    if not execution_row:
        raise ValueError("Execution not found")

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
    sessions = await db.execute(select(SessionMetric.state).where(SessionMetric.database_id == database.id, SessionMetric.collected_at >= window_start, SessionMetric.collected_at <= window_end))
    state_counts = {"active": 0, "idle": 0, "idle in transaction": 0, "waiting": 0}
    session_rows = sessions.all()
    # Deduplicate by considering the closest time or just use aggregate if they are all from the same snapshot.
    # A simple approach is just counting the latest snapshot within the window.
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
            func.lower(Query.hash) == query_hash.lower(),
        )
        .limit(1)
    )
    query_id = query_row_result.scalar_one_or_none()
    
    tables_response = []
    if query_id:
        table_hits_result = await db.execute(select(QueryTableHit.schema_name, QueryTableHit.table_name).where(QueryTableHit.query_id == query_id).distinct())
        table_hits = table_hits_result.all()
        
        for hit in table_hits:
            table_obj = await db.execute(select(Table).where(Table.database_id == database.id, Table.schema_name == hit.schema_name, Table.name == hit.table_name, Table.deleted_at.is_(None)).limit(1))
            t = table_obj.scalar_one_or_none()
            if not t:
                continue
            
            t_metric = await db.execute(select(TableMetric).where(TableMetric.table_id == t.id, TableMetric.collected_at <= window_end).order_by(TableMetric.collected_at.desc()).limit(1))
            tm = t_metric.scalar_one_or_none()
            
            indexes = []
            idx_result = await db.execute(select(Index).where(Index.table_id == t.id, Index.deleted_at.is_(None)))
            for idx in idx_result.scalars().all():
                idx_metric = await db.execute(select(IndexMetric).where(IndexMetric.index_id == idx.id, IndexMetric.collected_at <= window_end).order_by(IndexMetric.collected_at.desc()).limit(1))
                im = idx_metric.scalar_one_or_none()
                
                # Hit rate calculation: blks_hit / (blks_hit + blks_read)
                hit_rate = None
                if im and im.blks_hit is not None and im.blks_read is not None:
                    total_blks = im.blks_hit + im.blks_read
                    if total_blks > 0:
                        hit_rate = im.blks_hit / total_blks

                indexes.append(QueryContextIndex(
                    index_id=idx.id,
                    index_name=idx.name,
                    index_type=idx.type,
                    definition=idx.definition,
                    is_unique=idx.is_unique,
                    is_primary=idx.is_primary,
                    size_bytes=im.size if im else None,
                    scan_qt=im.scan_qt if im else None,
                    hit_rate=hit_rate,
                ))
            
            columns = []
            col_result = await db.execute(select(ColumnModel).where(ColumnModel.table_id == t.id, ColumnModel.deleted_at.is_(None)))
            for col in col_result.scalars().all():
                col_metric = await db.execute(select(ColumnMetric).where(ColumnMetric.column_id == col.id, ColumnMetric.collected_at <= window_end).order_by(ColumnMetric.collected_at.desc()).limit(1))
                cm = col_metric.scalar_one_or_none()
                columns.append(QueryContextColumn(
                    column_id=col.id,
                    name=col.name,
                    data_type=col.data_type,
                    is_nullable=col.is_nullable,
                    n_distinct=cm.n_distinct if cm else None,
                    null_fraction=cm.null_fraction if cm else None,
                    avg_width=cm.avg_width if cm else None,
                ))

            tables_response.append(QueryContextTable(
                table_id=t.id,
                schema_name=t.schema_name,
                table_name=t.name,
                n_live_tup=tm.n_live_tup if tm else None,
                n_dead_tup=tm.n_dead_tup if tm else None,
                seq_scan=tm.seq_scan if tm else None,
                idx_scan=tm.idx_scan if tm else None,
                last_vacuum=tm.last_vacuum if tm else None,
                last_autovacuum=tm.last_autovacuum if tm else None,
                last_analyze=tm.last_analyze if tm else None,
                last_autoanalyze=tm.last_autoanalyze if tm else None,
                size_bytes=tm.table_size_bytes if tm else None,
                indexes=indexes,
                columns=columns,
            ))
            
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
