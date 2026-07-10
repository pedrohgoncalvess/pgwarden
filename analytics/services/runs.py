import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.config import AnalyticsYamlConfig, load_analytics_config
from analytics.database import DatabaseConnection
from analytics.database.models.analytics import AnalyticsConfig, AnalyticsRun
from analytics.database.models.metadata import Database
from analytics.services.query_analysis import process_query_analysis_with_session
from analytics.services.query_hits import process_pending_native_queries_with_session

DEFAULT_RUN_INTERVAL_SECONDS = 30 * 60
MIN_RUN_INTERVAL_SECONDS = 10
POLL_INTERVAL_SECONDS = 10
QUERY_BATCH_SIZE = 500


@dataclass(frozen=True)
class AnalyticsRunResult:
    database_id: int
    processed_queries: int
    analyzed_queries: int
    error: str | None = None


@dataclass(frozen=True)
class AnalyticsRunRequest:
    run_id: int
    config_id: int
    database_id: int
    query_analysis_enabled: bool
    recommendation_enabled: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _effective_interval(seconds: int | None) -> int:
    if seconds is None:
        return DEFAULT_RUN_INTERVAL_SECONDS
    return max(MIN_RUN_INTERVAL_SECONDS, int(seconds))


async def run_due_analytics(active_database_ids: set[int] | None = None) -> list[AnalyticsRunRequest]:
    async with DatabaseConnection() as session:
        yaml_config = load_analytics_config()
        await sync_configs_with_session(session, yaml_config)
        return await prepare_due_analytics_with_session(session, active_database_ids or set())


async def run_analytics_loop(poll_interval: int = POLL_INTERVAL_SECONDS) -> None:
    active_tasks: dict[int, asyncio.Task[AnalyticsRunResult]] = {}

    while True:
        _clear_finished_tasks(active_tasks)
        requests = await run_due_analytics(active_database_ids=set(active_tasks))
        for request in requests:
            active_tasks[request.database_id] = asyncio.create_task(_execute_run_request(request))

        await asyncio.sleep(poll_interval)


async def sync_configs_with_session(session: AsyncSession, yaml_config: AnalyticsYamlConfig) -> None:
    active_databases = await _active_databases(session)
    if not active_databases:
        await session.commit()
        return

    config_by_database_id = await _configs_by_database_id(session)
    current_time = _now()

    for database in active_databases:
        database_name = database.db_name
        database_yaml = yaml_config.for_database(database_name)
        config = config_by_database_id.get(database.id)

        if config is None:
            session.add(
                AnalyticsConfig(
                    database_id=database.id,
                    run_interval=_effective_interval(database_yaml.interval),
                    last_seen=current_time,
                    query_analytics_enabled=database_yaml.query_analysis,
                    recommendation_enabled=database_yaml.recommendation,
                )
            )
            continue

        config.run_interval = _effective_interval(database_yaml.interval)
        config.query_analytics_enabled = database_yaml.query_analysis
        config.recommendation_enabled = database_yaml.recommendation
        config.last_seen = current_time

    await session.flush()

    config_database_ids = {database.id for database in active_databases}
    existing_run_database_ids = await _run_database_ids(session)
    for database_id in config_database_ids - existing_run_database_ids:
        session.add(AnalyticsRun(database_id=database_id, run_at=current_time))

    await session.commit()


async def prepare_due_analytics_with_session(
    session: AsyncSession,
    active_database_ids: set[int],
) -> list[AnalyticsRunRequest]:
    due_runs = await _due_runs(session, active_database_ids)
    requests: list[AnalyticsRunRequest] = []

    for run, config in due_runs:
        run_id = run.id
        database_id = run.database_id
        interval = _effective_interval(config.run_interval)
        next_run_at = _now() + timedelta(seconds=interval)
        session.add(AnalyticsRun(database_id=database_id, run_at=next_run_at))
        requests.append(
            AnalyticsRunRequest(
                run_id=run_id,
                config_id=config.id,
                database_id=database_id,
                query_analysis_enabled=config.query_analytics_enabled,
                recommendation_enabled=config.recommendation_enabled,
            )
        )

    await session.commit()
    return requests


async def _execute_run_request(request: AnalyticsRunRequest) -> AnalyticsRunResult:
    async with DatabaseConnection() as session:
        try:
            processed = 0
            analyzed = 0
            if request.query_analysis_enabled:
                processed = await process_pending_native_queries_with_session(
                    session,
                    limit=QUERY_BATCH_SIZE,
                    database_id=request.database_id,
                    commit=False,
                )
                analyzed = await process_query_analysis_with_session(
                    session,
                    run_id=request.run_id,
                    database_id=request.database_id,
                    include_recommendations=request.recommendation_enabled,
                )

            config = await session.get(AnalyticsConfig, request.config_id)
            if config is not None:
                config.last_seen = _now()

            await session.commit()
            result = AnalyticsRunResult(
                database_id=request.database_id,
                processed_queries=processed,
                analyzed_queries=analyzed,
            )
            print(
                "Analytics run processed "
                f"{result.processed_queries} queries and analyzed "
                f"{result.analyzed_queries} queries for database {result.database_id}"
            )
            return result
        except Exception as exc:
            await session.rollback()
            await _record_run_error(session, request.run_id, str(exc))
            result = AnalyticsRunResult(
                database_id=request.database_id,
                processed_queries=0,
                analyzed_queries=0,
                error=str(exc),
            )
            print(f"Analytics run failed for database {result.database_id}: {result.error}")
            return result


def _clear_finished_tasks(active_tasks: dict[int, asyncio.Task[AnalyticsRunResult]]) -> None:
    for database_id, task in list(active_tasks.items()):
        if not task.done():
            continue

        try:
            task.result()
        except Exception as exc:
            print(f"Analytics run task failed for database {database_id}: {exc}")
        del active_tasks[database_id]


async def _active_databases(session: AsyncSession) -> list[Database]:
    result = await session.execute(
        select(Database)
        .where(Database.is_active.is_(True))
        .where(Database.deleted_at.is_(None))
    )
    return list(result.scalars().all())


async def _configs_by_database_id(session: AsyncSession) -> dict[int, AnalyticsConfig]:
    result = await session.execute(select(AnalyticsConfig))
    return {config.database_id: config for config in result.scalars().all()}


async def _run_database_ids(session: AsyncSession) -> set[int]:
    result = await session.execute(select(AnalyticsRun.database_id))
    return set(result.scalars().all())


async def _due_runs(
    session: AsyncSession,
    active_database_ids: set[int],
) -> list[tuple[AnalyticsRun, AnalyticsConfig]]:
    latest_run_ids = (
        select(func.max(AnalyticsRun.id).label("id"))
        .group_by(AnalyticsRun.database_id)
        .subquery()
    )
    statement = (
        select(AnalyticsRun, AnalyticsConfig)
        .join(latest_run_ids, AnalyticsRun.id == latest_run_ids.c.id)
        .join(AnalyticsConfig, AnalyticsConfig.database_id == AnalyticsRun.database_id)
        .join(Database, Database.id == AnalyticsRun.database_id)
        .where(AnalyticsRun.run_at <= _now())
        .where(Database.is_active.is_(True))
        .where(Database.deleted_at.is_(None))
        .order_by(AnalyticsRun.run_at.asc())
        .with_for_update(skip_locked=True, of=AnalyticsRun)
    )

    if active_database_ids:
        statement = statement.where(AnalyticsRun.database_id.not_in(active_database_ids))

    result = await session.execute(statement)
    return list(result.all())


async def _record_run_error(
    session: AsyncSession,
    run_id: int,
    error: str,
) -> None:
    run = await session.get(AnalyticsRun, run_id)
    if run is not None:
        run.error = error

    await session.commit()
