import asyncio

from psycopg.rows import dict_row

from collector.collectors import (
    TableCollector,
    IndexCollector,
    ColumnCollector,
    TableMetricCollector,
    IndexMetricCollector,
    ColumnMetricCollector,
    LockMetricCollector,
    SessionMetricCollector,
    DatabaseStatCollector,
    NativeQueryMetricCollector,
    CpuCollector,
    RamCollector,
    DiskCollector,
    IoCollector,
)
from database import DatabaseConnection, DatabaseRegistry
from database.heartbeat import touch_heartbeat
from database.storage import get_storage_connection
from scheduler import queries
from scheduler.startup import run_startup_collectors
from scheduler.loops import run_database_collector_loop, run_server_collector_loop
from config import bootstrap
from log import logger
from collector.collectors.metric.query_workload import QueryWorkloadMetricCollector


DATABASE_COLLECTOR_MAP = {
    "query_workload_collector": lambda mon, met, db: QueryWorkloadMetricCollector(mon, met, db.id),
    "table_collector": lambda mon, met, db: TableCollector(mon, met, db),
    "column_collector": lambda mon, met, db: ColumnCollector(mon, met, db),
    "index_collector": lambda mon, met, db: IndexCollector(mon, met, db),
    "table_metric_collector": lambda mon, met, db: TableMetricCollector(
        mon, met, db.id
    ),
    "column_metric_collector": lambda mon, met, db: ColumnMetricCollector(
        mon, met, db.id
    ),
    "index_metric_collector": lambda mon, met, db: IndexMetricCollector(
        mon, met, db.id
    ),
    "lock_metric_collector": lambda mon, met, db: LockMetricCollector(mon, met, db.id),
    "session_metric_collector": lambda mon, met, db: SessionMetricCollector(
        mon, met, db.id
    ),
    "database_stat_collector": lambda mon, met, db: DatabaseStatCollector(
        mon, met, db.id
    ),
    "native_query_collector": lambda mon, met, db: NativeQueryMetricCollector(
        mon, met, db.id
    ),
}

SERVER_COLLECTOR_MAP = {
    "cpu_collector": lambda met, sid: CpuCollector(met, sid),
    "ram_collector": lambda met, sid: RamCollector(met, sid),
    "disk_collector": lambda met, sid: DiskCollector(met, sid),
    "io_collector": lambda met, sid: IoCollector(met, sid),
}


async def main() -> None:
    """Start collection against the explicitly selected storage backend."""
    metrics_db = get_storage_connection()
    registry = DatabaseRegistry(metrics_db=metrics_db)

    await bootstrap(metrics_db)
    await registry.sync()

    async with metrics_db as conn:
        await touch_heartbeat(conn)

    async def registry_sync_loop() -> None:
        while True:
            try:
                await registry.sync()
                async with metrics_db as conn:
                    await touch_heartbeat(conn)
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
            await logger.error(
                "Main",
                "startup",
                f"Failed initial sync db_id={db.id}. Skipping loops. Error: {startup_error}",
            )
            continue

        async with metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(queries.GET_DB_CONFIGS_BY_DB, {"database_id": db.id})
                config_rows = await cur.fetchall()

        for cfg in config_rows:
            factory = DATABASE_COLLECTOR_MAP.get(cfg["name"])
            if not factory:
                await logger.error(
                    "Main",
                    "startup",
                    f"Unknown collector name '{cfg['name']}' for db_id={db.id}",
                )
                continue

            collector_instance = factory(monitored_db, metrics_db, db)
            task = asyncio.create_task(
                run_database_collector_loop(
                    metrics_db=metrics_db,
                    collector=collector_instance,
                    config_id=cfg["id"],
                    name=f"{cfg['name']}:db{db.id}",
                    database_id=db.id,
                )
            )
            background_tasks.add(task)

    for server_id in registry.server_ids():
        async with metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    queries.GET_SRV_CONFIGS_BY_SRV, {"server_id": server_id}
                )
                srv_config_rows = await cur.fetchall()

        for cfg in srv_config_rows:
            factory = SERVER_COLLECTOR_MAP.get(cfg["name"])
            if not factory:
                await logger.error(
                    "Main",
                    "startup",
                    f"Unknown server collector '{cfg['name']}' for server_id={server_id}",
                )
                continue

            collector_instance = factory(metrics_db, server_id)
            task = asyncio.create_task(
                run_server_collector_loop(
                    metrics_db=metrics_db,
                    collector=collector_instance,
                    config_id=cfg["id"],
                    name=f"{cfg['name']}:srv{server_id}",
                    server_id=server_id,
                )
            )
            background_tasks.add(task)

    await logger.info(
        "Main",
        "startup",
        f"Started {len(background_tasks)} independent collector loops",
    )

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
