"""Combine compact statement summaries with sampled activity analytics."""

from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.analytics.query.aggregation import fetch_query_groups
from app.databases.analytics.query.models import (
    QueryAnalyticsFilters, QueryAnalyticsItem, QueryAnalyticsTimelinePoint,
)
from app.databases.analytics.query.statement_aggregation import (
    build_statement_bundle, build_statement_timeline, fetch_compact_statements,
)
from app.databases.analytics.query.summaries import summarize_queries


def build_statement_group(row: Row) -> SimpleNamespace:
    """Adapt compact SQL totals to the common summary representation."""
    data = {key: value for key, value in row._mapping.items() if key != "kind"}
    data.update(execution_count=int(row.execution_count), duration_count=int(row.duration_count))
    return SimpleNamespace(
        **data, application_name=None, source="statements",
        duration_min=None, duration_max=None, skip_timeline=True,
    )


def _matching_texts(
    groups: list, normalize: Callable[[str | None], str],
    search: list[str], exclude: list[str],
) -> list[str]:
    normalized = {}
    matches = set()
    for row in groups:
        key = (row.query_hash, row.query if row.query_hash is None else None)
        if key not in normalized:
            normalized[key] = normalize(row.query)
        signature = normalized[key]
        if (signature and (not search or any(term in signature for term in search))
                and not any(term in signature for term in exclude)
                and getattr(row, "source", "activity") == "statements"):
            matches.add(row.query)
    return sorted(matches)


async def fetch_analytics(
    db: AsyncSession, database_id: int, start_at: datetime, end_at: datetime,
    user_name: str | None, application_name: str | None, state: str | None,
    normalize: Callable[[str | None], str], search: list[str], exclude: list[str],
    limit: int | None, order_by: str, order_dir: str,
) -> tuple[list[QueryAnalyticsItem], list[QueryAnalyticsTimelinePoint], int, QueryAnalyticsFilters]:
    """Keep transfer bounded by summaries and actual timeline intervals."""
    groups, filters = await fetch_query_groups(
        db, database_id, start_at, end_at, user_name, application_name, state,
    )
    statement_timeline = None
    if application_name is None and state is None:
        if not search and not exclude:
            bundle = list(await db.execute(build_statement_bundle(
                database_id, start_at, end_at, user_name,
            )))
            statements = [row for row in bundle if row.kind == "summary"]
            statement_timeline = [row for row in bundle if row.kind == "timeline"]
        else:
            statements = await fetch_compact_statements(
                db, database_id, start_at, end_at, user_name,
            )
        groups.extend(build_statement_group(row) for row in statements)
        filters.users = sorted(
            set(filters.users) | {row.user_name for row in statements},
            key=lambda value: (value is None, value or ""),
        )
    items, timeline, total = summarize_queries(
        groups, normalize, search, exclude, limit, order_by, order_dir,
    )
    texts = _matching_texts(groups, normalize, search, exclude)
    if texts:
        all_texts = {row.query for row in groups if getattr(row, "source", "activity") == "statements"}
        if statement_timeline is not None and set(texts) == all_texts:
            result = [SimpleNamespace(
                timestamp=row.last_seen, interval_start=row.first_seen,
                execution_count=row.execution_count, duration_sum=row.duration_sum,
            ) for row in statement_timeline]
        else:
            result = await db.execute(build_statement_timeline(
                database_id, start_at, end_at, user_name,
                sorted({row.text_key for row in groups
                        if getattr(row, "source", "activity") == "statements"
                        and row.query in texts}),
            ))
        timeline.extend(QueryAnalyticsTimelinePoint(
            timestamp=row.timestamp, interval_start=row.interval_start,
            source="statements", execution_count=row.execution_count,
            avg_duration_ms=row.duration_sum / int(row.execution_count) if row.execution_count else None,
        ) for row in result)
        timeline.sort(key=lambda point: (point.timestamp, point.source, point.interval_start))
    return items, timeline, total, filters
