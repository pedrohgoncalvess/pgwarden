import asyncio
from datetime import datetime, timezone

from psycopg.rows import dict_row

from collector.collectors import (
    TableCollector, IndexCollector, ColumnCollector,
    TableMetricCollector, IndexMetricCollector, ColumnMetricCollector,
    LockMetricCollector, SessionMetricCollector,
    CpuCollector, RamCollector, DiskCollector, IoCollector,
)
from database import (
    DatabaseConnection, DatabaseRegistry,
    load_storage_query, MonitoredDatabase
)
from config import bootstrap
from log import logger


_GET_DB_CONFIG = load_storage_query(schema="collector", table="config_database", query_type="SELECT", query_name="by_id")
_GET_DB_CONFIGS_BY_DB = load_storage_query(schema="collector", table="config_database", query_type="SELECT", query_name="by_database_id")
_SET_DB_RUNNING = load_storage_query(schema="collector", table="config_database", query_type="UPDATE", query_name="running")
_SET_DB_SUCCESS = load_storage_query(schema="collector", table="config_database", query_type="UPDATE", query_name="success")
_SET_DB_ERROR = load_storage_query(schema="collector", table="config_database", query_type="UPDATE", query_name="error")
_SET_DB_FORCE = load_storage_query(schema="collector", table="config_database", query_type="UPDATE", query_name="set_next_run_on_force")

_GET_SRV_CONFIG = load_storage_query(schema="collector", table="config_server", query_type="SELECT", query_name="by_id")
_GET_SRV_CONFIGS_BY_SRV = load_storage_query(schema="collector", table="config_server", query_type="SELECT", query_name="by_server_id")
_SET_SRV_RUNNING = load_storage_query(schema="collector", table="config_server", query_type="UPDATE", query_name="running")
_SET_SRV_SUCCESS = load_storage_query(schema="collector", table="config_server", query_type="UPDATE", query_name="success")
_SET_SRV_ERROR = load_storage_query(schema="collector", table="config_server", query_type="UPDATE", query_name="error")
_SET_SRV_FORCE = load_storage_query(schema="collector", table="config_server", query_type="UPDATE", query_name="set_next_run_on_force")

_CONSUME_COMMAND = load_storage_query(schema="collector", table="command", query_type="UPDATE", query_name="consume_command")
_INSERT_RUN_SUCCESS_DB = load_storage_query(schema="collector", table="run", query_type="INSERT", query_name="success_database")
_INSERT_RUN_ERROR_DB = load_storage_query(schema="collector", table="run", query_type="INSERT", query_name="error_database")
_INSERT_RUN_SUCCESS_SRV = load_storage_query(schema="collector", table="run", query_type="INSERT", query_name="success_server")
_INSERT_RUN_ERROR_SRV = load_storage_query(schema="collector", table="run", query_type="INSERT", query_name="error_server")


DATABASE_COLLECTOR_MAP = {
    "table_collector":           lambda mon, met, db: TableCollector(mon, met, db),
    "column_collector":          lambda mon, met, db: ColumnCollector(mon, met, db),
    "index_collector":           lambda mon, met, db: IndexCollector(mon, met, db),
    "table_metric_collector":    lambda mon, met, db: TableMetricCollector(mon, met, db.id),
    "column_metric_collector":   lambda mon, met, db: ColumnMetricCollector(mon, met, db.id),
    "index_metric_collector":    lambda mon, met, db: IndexMetricCollector(mon, met, db.id),
    "lock_metric_collector":     lambda mon, met, db: LockMetricCollector(mon, met, db.id),
    "session_metric_collector":  lambda mon, met, db: SessionMetricCollector(mon, met, db.id),
}

SERVER_COLLECTOR_MAP = {
    "cpu_collector":  lambda met, sid: CpuCollector(met, sid),
    "ram_collector":  lambda met, sid: RamCollector(met, sid),
    "disk_collector": lambda met, sid: DiskCollector(met, sid),
    "io_collector":   lambda met, sid: IoCollector(met, sid),
}


async def _run_collector_loop(
        metrics_db: DatabaseConnection,
        collector,
        config_id: int,
        name: str,
        q_get_config,
        q_running,
        q_success,
        q_error,
        q_force,
        q_run_success,
        q_run_error,
) -> None:
    while True:
        try:
            async with metrics_db as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(_CONSUME_COMMAND, {"name": name})
                    cmd_row = await cur.fetchone()
                await conn.commit()

            command = cmd_row["command"] if cmd_row else None
            command_id = cmd_row["id"] if cmd_row else None
            is_force_run = command == "force_run"

            async with metrics_db as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(q_get_config, {"id": config_id})
                    config = await cur.fetchone()

                if not config:
                    await logger.error("Orchestrator", name, f"Config id={config_id} not found. Stopping.")
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
                            await cur.execute(q_force, {"id": config_id})
                            await conn.commit()

                async with metrics_db as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(q_running, {"id": config_id})
                        await conn.commit()

                await collector.collect()

                async with metrics_db as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(q_success, {"id": config_id})
                        await cur.execute(q_run_success, {
                            "config_id": config_id,
                            "command_id": command_id if is_force_run else None,
                        })
                        await conn.commit()

            else:
                if is_paused:
                    sleep_seconds = 2.0
                else:
                    sleep_seconds = (next_run - now).total_seconds()

                sleep_seconds = min(sleep_seconds, 2.0)
                await asyncio.sleep(max(0, sleep_seconds))

        except Exception as error:
            try:
                async with metrics_db as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(q_error, {"id": config_id})
                        await cur.execute(q_run_error, {
                            "config_id": config_id,
                            "command_id": command_id if is_force_run else None,
                            "errors": [str(error)],
                        })
                        await conn.commit()
            except Exception:
                pass

            await logger.error("Orchestrator", name, f"Execution failed: {error}")
            await asyncio.sleep(2)


def run_database_collector_loop(metrics_db, collector, config_id, name):
    return _run_collector_loop(
        metrics_db=metrics_db,
        collector=collector,
        config_id=config_id,
        name=name,
        q_get_config=_GET_DB_CONFIG,
        q_running=_SET_DB_RUNNING,
        q_success=_SET_DB_SUCCESS,
        q_error=_SET_DB_ERROR,
        q_force=_SET_DB_FORCE,
        q_run_success=_INSERT_RUN_SUCCESS_DB,
        q_run_error=_INSERT_RUN_ERROR_DB,
    )


def run_server_collector_loop(metrics_db, collector, config_id, name):
    return _run_collector_loop(
        metrics_db=metrics_db,
        collector=collector,
        config_id=config_id,
        name=name,
        q_get_config=_GET_SRV_CONFIG,
        q_running=_SET_SRV_RUNNING,
        q_success=_SET_SRV_SUCCESS,
        q_error=_SET_SRV_ERROR,
        q_force=_SET_SRV_FORCE,
        q_run_success=_INSERT_RUN_SUCCESS_SRV,
        q_run_error=_INSERT_RUN_ERROR_SRV,
    )


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


async def main() -> None:
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

        async with metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_GET_DB_CONFIGS_BY_DB, {"database_id": db.id})
                config_rows = await cur.fetchall()

        for cfg in config_rows:
            factory = DATABASE_COLLECTOR_MAP.get(cfg["name"])
            if not factory:
                await logger.error("Main", "startup", f"Unknown collector name '{cfg['name']}' for db_id={db.id}")
                continue

            collector_instance = factory(monitored_db, metrics_db, db)
            task = asyncio.create_task(
                run_database_collector_loop(
                    metrics_db=metrics_db,
                    collector=collector_instance,
                    config_id=cfg["id"],
                    name=f"{cfg['name']}:db{db.id}",
                )
            )
            background_tasks.add(task)

    for server_id in registry.server_ids():
        async with metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_GET_SRV_CONFIGS_BY_SRV, {"server_id": server_id})
                srv_config_rows = await cur.fetchall()

        for cfg in srv_config_rows:
            factory = SERVER_COLLECTOR_MAP.get(cfg["name"])
            if not factory:
                await logger.error("Main", "startup", f"Unknown server collector '{cfg['name']}' for server_id={server_id}")
                continue

            collector_instance = factory(metrics_db, server_id)
            task = asyncio.create_task(
                run_server_collector_loop(
                    metrics_db=metrics_db,
                    collector=collector_instance,
                    config_id=cfg["id"],
                    name=f"{cfg['name']}:srv{server_id}",
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