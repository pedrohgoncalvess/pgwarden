"""Aggregate query snapshots in SQL before transferring them to the API."""

from datetime import datetime

from sqlalchemy import Row, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.databases.analytics.query.models import QueryAnalyticsFilters
from database.models.metric.native_query import NativeQueryMetric as Sample


def _group_executions(filters: list) -> Select:
    execution_start = func.coalesce(Sample.query_start, Sample.collected_at)
    executions = (
        select(
            Sample.pid, Sample.backend_start, Sample.query_hash,
            func.min(Sample.collected_at).label("first_seen"),
            func.max(Sample.collected_at).label("last_seen"),
            func.avg(Sample.query_duration_ms).label("duration"),
        )
        .where(*filters)
        .group_by(
            Sample.pid, Sample.backend_start, execution_start, Sample.query_hash,
        )
        .cte("executions")
    )
    bucket = func.floor(func.extract("epoch", executions.c.first_seen) / 300)
    # Missing hashes must not merge unrelated SQL into the same representative.
    unhashed_query = case((Sample.query_hash.is_(None), Sample.query))
    return (
        select(
            Sample.query_hash, func.min(Sample.query).label("query"),
            Sample.user_name, Sample.application_name, bucket.label("bucket"),
            func.count().label("execution_count"),
            func.count(executions.c.duration).label("duration_count"),
            func.sum(executions.c.duration).label("duration_sum"),
            func.min(executions.c.duration).label("duration_min"),
            func.max(executions.c.duration).label("duration_max"),
            func.min(executions.c.first_seen).label("first_seen"),
            func.max(executions.c.last_seen).label("last_seen"),
        )
        .select_from(executions)
        .join(Sample, and_(
            Sample.pid == executions.c.pid,
            Sample.backend_start == executions.c.backend_start,
            Sample.collected_at == executions.c.first_seen,
        ))
        .where(*filters)
        .group_by(
            Sample.query_hash, unhashed_query,
            Sample.user_name, Sample.application_name, bucket,
        )
        .order_by(func.min(executions.c.first_seen))
    )


async def fetch_query_groups(
    db: AsyncSession, database_id: int, start_at: datetime, end_at: datetime,
    user_name: str | None, application_name: str | None, state: str | None,
) -> tuple[list[Row], QueryAnalyticsFilters]:
    """Return execution statistics and filter choices using two SQL queries."""
    filters = [
        Sample.database_id == database_id,
        Sample.collected_at >= start_at, Sample.collected_at <= end_at,
    ]
    for field, value in (
        (Sample.user_name, user_name), (Sample.application_name, application_name),
        (Sample.state, state),
    ):
        if value is not None:
            filters.append(field == value)

    groups = list((await db.execute(_group_executions(filters))).all())
    choices = (await db.execute(
        select(Sample.user_name, Sample.application_name, Sample.state)
        .where(*filters).distinct()
    )).all()

    def sort_values(values: set[str | None]) -> list[str | None]:
        return sorted(values, key=lambda value: (value is None, value or ""))

    return groups, QueryAnalyticsFilters(
        users=sort_values({row.user_name for row in choices}),
        applications=sort_values({row.application_name for row in choices}),
        states=sort_values({row.state for row in choices}),
    )
