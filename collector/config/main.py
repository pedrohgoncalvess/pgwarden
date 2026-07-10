from psycopg.rows import dict_row

from config.load import _load_config
from config.upsert import _upsert_server, _upsert_database
from database import DatabaseConnection, load_storage_query
from log import logger


DEFAULT_COLLECTOR_SETTINGS = {
    "table_collector": {"interval": 1800, "enabled": True},
    "column_collector": {"interval": 1800, "enabled": True},
    "index_collector": {"interval": 1800, "enabled": True},
    "table_metric_collector": {"interval": 1800, "enabled": True},
    "column_metric_collector": {"interval": 1800, "enabled": True},
    "index_metric_collector": {"interval": 1800, "enabled": True},
    "database_stat_collector": {"interval": 3, "enabled": True},
    "lock_metric_collector": {"interval": 3, "enabled": True},
    "session_metric_collector": {"interval": 3, "enabled": True},
    "native_query_collector": {"interval": 0.5, "enabled": True},
    "cpu_collector": {"interval": 20, "enabled": True},
    "ram_collector": {"interval": 20, "enabled": True},
    "io_collector": {"interval": 5, "enabled": True},
    "disk_collector": {"interval": 1800, "enabled": True},
}

_GET_ALL_DB_CONFIGS = load_storage_query(
    schema="collector", table="config_database", query_type="SELECT", query_name="all"
)
_GET_ALL_SRV_CONFIGS = load_storage_query(
    schema="collector", table="config_server", query_type="SELECT", query_name="all"
)
_UPDATE_DB_SETTINGS = load_storage_query(
    schema="collector",
    table="config_database",
    query_type="UPDATE",
    query_name="set_settings",
)
_UPDATE_SRV_SETTINGS = load_storage_query(
    schema="collector",
    table="config_server",
    query_type="UPDATE",
    query_name="set_settings",
)
_DELETE_SRV_CONFIGS = load_storage_query(
    schema="collector",
    table="config_server",
    query_type="DELETE",
    query_name="by_server_id",
)


def _resolve_collector_settings(collector_config: dict | None) -> dict:
    if not collector_config:
        return {}

    settings = {}
    for name, cfg in collector_config.items():
        if name not in DEFAULT_COLLECTOR_SETTINGS:
            continue
        if not isinstance(cfg, dict):
            continue

        defaults = DEFAULT_COLLECTOR_SETTINGS[name]
        settings[name] = {
            "interval": cfg.get("interval", defaults["interval"]),
            "enabled": cfg.get("enabled", defaults["enabled"]),
        }

    return settings


async def _apply_collector_settings(metrics_db: DatabaseConnection) -> None:
    config = _load_config()
    collector_config = config.get("collector")
    settings = _resolve_collector_settings(collector_config)

    if not settings:
        return

    async with metrics_db as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_GET_ALL_DB_CONFIGS)
            db_rows = await cur.fetchall()
            for row in db_rows:
                name = row["name"]
                if name not in settings:
                    continue
                cfg = settings[name]
                await cur.execute(
                    _UPDATE_DB_SETTINGS,
                    {
                        "id": row["id"],
                        "interval": cfg["interval"],
                        "is_paused": not cfg["enabled"],
                    },
                )

            await cur.execute(_GET_ALL_SRV_CONFIGS)
            srv_rows = await cur.fetchall()
            for row in srv_rows:
                name = row["name"]
                if name not in settings:
                    continue
                cfg = settings[name]
                await cur.execute(
                    _UPDATE_SRV_SETTINGS,
                    {
                        "id": row["id"],
                        "interval": cfg["interval"],
                        "is_paused": not cfg["enabled"],
                    },
                )

        await conn.commit()

    await logger.info(
        "Bootstrap",
        "collector_settings",
        f"Applied settings for {len(settings)} collector(s)",
    )


async def bootstrap(metrics_db: DatabaseConnection) -> None:
    config = _load_config()
    servers = config.get("servers")

    if not servers:
        await logger.info("Bootstrap", "config", "No servers in config.yaml — skipping")
        return

    disabled_server_metrics: list[int] = []

    async with metrics_db as conn:
        for entry in servers:
            try:
                row = await _upsert_server(conn, entry)
                for db_name in entry.get("databases", []):
                    await _upsert_database(conn, row, db_name)

                if not entry.get("server_metrics_enabled", True):
                    disabled_server_metrics.append(row)

            except Exception as error:
                await logger.error(
                    "Bootstrap", entry.get("name", "?"), f"Failed: {error}"
                )
                continue

        await conn.commit()

    if disabled_server_metrics:
        async with metrics_db as conn:
            async with conn.cursor() as cur:
                for server_id in disabled_server_metrics:
                    await cur.execute(_DELETE_SRV_CONFIGS, {"server_id": server_id})
            await conn.commit()

        await logger.info(
            "Bootstrap",
            "server_metrics",
            f"Removed server collectors for {len(disabled_server_metrics)} server(s)",
        )

    await _apply_collector_settings(metrics_db)
