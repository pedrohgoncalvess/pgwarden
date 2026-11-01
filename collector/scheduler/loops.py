"""Run independently scheduled collectors against the selected storage."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Coroutine

from psycopg.rows import dict_row

from database.storage import StorageConnection
from log import logger
from scheduler import queries


async def _run_collector_loop(
    metrics_db: StorageConnection,
    collector: Any,
    config_id: int,
    name: str,
    q_get_config: str,
    q_running: str,
    q_success: str,
    q_error: str,
    q_force: str,
    q_run_success: str,
    q_run_error: str,
    q_last_seen_db: str,
    q_last_seen_srv: str,
    database_id: int | None = None,
    server_id: int | None = None,
) -> None:
    while True:
        try:
            async with metrics_db as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(queries.CONSUME_COMMAND, {"name": name})
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
                    await logger.error(
                        "Orchestrator",
                        name,
                        f"Config id={config_id} not found. Stopping.",
                    )
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
                        await cur.execute(
                            q_run_success,
                            {
                                "config_id": config_id,
                                "command_id": command_id if is_force_run else None,
                            },
                        )
                        if database_id is not None:
                            await cur.execute(
                                q_last_seen_db, {"id": database_id, "error": None}
                            )
                        if server_id is not None:
                            await cur.execute(
                                q_last_seen_srv, {"server_id": server_id, "error": None}
                            )
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
                        await cur.execute(
                            q_run_error,
                            {
                                "config_id": config_id,
                                "command_id": command_id if is_force_run else None,
                                "errors": [str(error)],
                            },
                        )
                        if database_id is not None:
                            await cur.execute(
                                q_last_seen_db, {"id": database_id, "error": str(error)}
                            )
                        if server_id is not None:
                            await cur.execute(
                                q_last_seen_srv,
                                {"server_id": server_id, "error": str(error)},
                            )
                        await conn.commit()
            except Exception:
                pass

            await logger.error("Orchestrator", name, f"Execution failed: {error}")
            await asyncio.sleep(2)


def run_database_collector_loop(
    metrics_db: StorageConnection,
    collector: Any,
    config_id: int,
    name: str,
    database_id: int | None = None,
    server_id: int | None = None,
) -> Coroutine[Any, Any, None]:
    """Run one database collector using its persisted schedule and commands."""
    return _run_collector_loop(
        metrics_db=metrics_db,
        collector=collector,
        config_id=config_id,
        name=name,
        q_get_config=queries.GET_DB_CONFIG,
        q_running=queries.SET_DB_RUNNING,
        q_success=queries.SET_DB_SUCCESS,
        q_error=queries.SET_DB_ERROR,
        q_force=queries.SET_DB_FORCE,
        q_run_success=queries.INSERT_RUN_SUCCESS_DB,
        q_run_error=queries.INSERT_RUN_ERROR_DB,
        q_last_seen_db=queries.UPDATE_LAST_SEEN_DB,
        q_last_seen_srv=queries.UPDATE_LAST_SEEN_SRV,
        database_id=database_id,
        server_id=server_id,
    )


def run_server_collector_loop(
    metrics_db: StorageConnection,
    collector: Any,
    config_id: int,
    name: str,
    database_id: int | None = None,
    server_id: int | None = None,
) -> Coroutine[Any, Any, None]:
    """Run one system collector using its persisted schedule and commands."""
    return _run_collector_loop(
        metrics_db=metrics_db,
        collector=collector,
        config_id=config_id,
        name=name,
        q_get_config=queries.GET_SRV_CONFIG,
        q_running=queries.SET_SRV_RUNNING,
        q_success=queries.SET_SRV_SUCCESS,
        q_error=queries.SET_SRV_ERROR,
        q_force=queries.SET_SRV_FORCE,
        q_run_success=queries.INSERT_RUN_SUCCESS_SRV,
        q_run_error=queries.INSERT_RUN_ERROR_SRV,
        q_last_seen_db=queries.UPDATE_LAST_SEEN_DB,
        q_last_seen_srv=queries.UPDATE_LAST_SEEN_SRV,
        database_id=database_id,
        server_id=server_id,
    )
