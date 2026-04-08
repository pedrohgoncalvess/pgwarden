import asyncio
import os
import time
import random
from urllib.parse import quote_plus
from datetime import datetime, timezone

from psycopg.rows import dict_row

from collector.collectors import (
    TableCollector, IndexCollector, ColumnCollector,
    TableMetricCollector, IndexMetricCollector, ColumnMetricCollector,
    LockMetricCollector, SessionMetricCollector
)
from database import (
    DatabaseConnection, DatabaseRegistry,
    load_storage_query, MonitoredDatabase
)
from config import bootstrap
from log import logger
from utils import get_env_var
from yoyo import read_migrations, get_backend


_GET_CONFIG = load_storage_query(schema="collector", table="config", query_type="SELECT", query_name="config")
_SET_STATUS_RUNNING = load_storage_query(schema="collector", table="config", query_type="UPDATE", query_name="running")
_SET_STATUS_SUCCESS = load_storage_query(schema="collector", table="config", query_type="UPDATE", query_name="success")
_SET_STATUS_ERROR = load_storage_query(schema="collector", table="config", query_type="UPDATE", query_name="error")
_SET_STATUS_PAUSED = load_storage_query(schema="collector", table="config", query_type="UPDATE", query_name="paused")
_CONSUME_COMMAND = load_storage_query(schema="collector", table="command", query_type="UPDATE", query_name="consume_command")
_SET_NEXT_RUN_ON_FORCE = load_storage_query(schema="collector", table="config", query_type="UPDATE", query_name="set_next_run_on_force")

async def run_collector_loop(
        metrics_db: DatabaseConnection,
        collector,
        name: str,
) -> None:
    while True:
        try:
            async with metrics_db as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(_CONSUME_COMMAND, {"name": name})
                    cmd_row = await cur.fetchone()
                await conn.commit()

            command = cmd_row["command"] if cmd_row else None
            is_force_run = command == "force_run"

            async with metrics_db as conn:
                async with conn.cursor() as cur:
                    await cur.execute(_GET_CONFIG, {"name": name})
                    config = await cur.fetchone()
                    await conn.commit()

                if not config:
                    await logger.error("Orchestrator", name, "Config not found. Stopping.")
                    break

                is_paused = config["is_paused"]
                next_run = config["next_run_at"]
                now = datetime.now(timezone.utc)

            should_run = False

            if is_force_run:
                should_run = True
            elif not is_paused and now >= next_run:
                should_run = True

            if should_run:
                if is_force_run:
                    async with metrics_db as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(_SET_NEXT_RUN_ON_FORCE, {"name": name})
                            await conn.commit()

                async with metrics_db as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(_SET_STATUS_RUNNING, {"name": name})
                        await conn.commit()

                await collector.collect()

                async with metrics_db as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(_SET_STATUS_SUCCESS, {"name": name})
                        await conn.commit()

            else:
                if is_paused:
                    sleep_seconds = 15.0
                else:
                    sleep_seconds = (next_run - now).total_seconds()

                sleep_seconds = min(sleep_seconds, 15.0)
                await asyncio.sleep(max(0, sleep_seconds))

        except Exception as error:
            try:
                async with metrics_db as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(_SET_STATUS_ERROR, {"name": name, "error": str(error)})
                        await conn.commit()
            except Exception:
                pass

            await logger.error("Orchestrator", name, f"Execution failed: {error}")
            await asyncio.sleep(2)


async def run_startup_collectors(
        monitored_db: DatabaseConnection,
        metrics_db: DatabaseConnection,
        db: MonitoredDatabase,
) -> None:
    await logger.info("Main", "startup_sync", f"Running initial schema sync (db_id={db.id})")

    startup_collectors = [
        ("tables", TableCollector(monitored_db, metrics_db, db)),
        ("columns", ColumnCollector(monitored_db, metrics_db, db)),
        ("indexes", IndexCollector(monitored_db, metrics_db, db)),
    ]

    for name, collector in startup_collectors:
        try:
            await collector.collect()
            await logger.info("Main", "startup_sync", f"{name} synced successfully")
        except Exception as error:
            await logger.error("Main", "startup_sync", f"{name} failed on startup: {error}")
            raise


def run_migrations() -> None:
    time.sleep(random.uniform(1.0, 3.0))
    logger.info("Main", "migrations", "Starting database migrations (collector)")
    host = get_env_var("DB_HOST")
    port = get_env_var("DB_PORT")
    user = get_env_var("DB_USER")
    password = quote_plus(get_env_var("DB_PASSWORD"))
    dbname = get_env_var("DB_NAME")

    db_url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"
    migrations_dir = os.path.join(os.path.dirname(__file__), "database", "migrations")

    backend = get_backend(db_url, migration_table='_yoyo_migration_collector')
    migrations = read_migrations(migrations_dir)

    backend.apply_migrations(backend.to_apply(migrations))
    logger.info("Main", "migrations", "Migrations completed successfully")


async def main() -> None:
    run_migrations()
    metrics_db = DatabaseConnection()
    registry = DatabaseRegistry(metrics_db=metrics_db)

    await bootstrap(metrics_db)
    await registry.sync()

    async def registry_sync_loop():
        while True:
            try:
                await registry.sync()
            except Exception as e:
                await logger.error("Main", "registry_sync", str(e))
            await asyncio.sleep(30)

    background_tasks = set()
    background_tasks.add(asyncio.create_task(registry_sync_loop()))

    for db in registry.all():
        monitored_db = DatabaseConnection(conninfo=db.conninfo)

        try:
            await run_startup_collectors(monitored_db, metrics_db, db)
        except Exception as startup_error:
            await logger.error("Main", "startup", f"Failed initial sync db_id={db.id}. Skipping loops. Error: {startup_error}")
            continue

        collectors_to_loop = [
            (TableCollector(monitored_db, metrics_db, db), "table_collector"),
            (ColumnCollector(monitored_db, metrics_db, db), "column_collector"),
            (IndexCollector(monitored_db, metrics_db, db), "index_collector"),
            (TableMetricCollector(monitored_db, metrics_db, db.id), "table_metric_collector"),
            (ColumnMetricCollector(monitored_db, metrics_db, db.id), "column_metric_collector"),
            (IndexMetricCollector(monitored_db, metrics_db, db.id), "index_metric_collector"),
            (LockMetricCollector(monitored_db, metrics_db, db.id), "lock_metric_collector"),
            (SessionMetricCollector(monitored_db, metrics_db, db.id), "session_metric_collector"),
        ]

        for collector_instance, collector_name in collectors_to_loop:
            task = asyncio.create_task(
                run_collector_loop(
                    metrics_db=metrics_db,
                    collector=collector_instance,
                    name=collector_name
                )
            )
            background_tasks.add(task)

    await logger.info("Main", "startup", f"Started {len(background_tasks)} independent collector loops")

    try:
        await asyncio.gather(*background_tasks)
    except asyncio.CancelledError:
        pass

    await logger.info("Main", "shutdown", "Shutting down")
    await DatabaseConnection.shutdown()


def _run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    _run()