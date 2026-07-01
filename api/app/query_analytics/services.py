import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.query_analytics.models import (
    QueryAnalyticsResponse,
    QueryAnalyticsItem,
    QueryAnalyticsTimelinePoint,
    QueryAnalyticsFilters,
    QueryAnalyticsUserBreakdown,
    QueryAnalyticsApplicationBreakdown,
)
from app.schemas.exceptions import DatabaseNotFoundError
from database.models.metadata.database import Database
from database.models.metric.native_query import NativeQueryMetric
from utils import decrypt_or_plain


PRESET_RANGES = {
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
    "2w": timedelta(weeks=2),
    "1m": timedelta(days=30),
}

# Pre-compiled regex patterns for query normalization.
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
    search: Optional[str],
    exclude: Optional[List[str]],
    limit: Optional[int] = 50,
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

    search_lower = search.lower() if search else None
    exclude_terms = [term.strip().lower() for term in (exclude or []) if term.strip()]

    # Stream rows in keyset-based batches to avoid OFFSET and large memory spikes.
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

            if search_lower and search_lower not in signature:
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

    # Aggregate by query signature.
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
    sorted_signatures = sorted(signatures.items(), key=lambda x: x[1]["execution_count"], reverse=True)
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
