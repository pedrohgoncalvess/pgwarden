import psycopg

from config.load import _load_config
from config.upsert import _upsert_server, _upsert_database
from database import DatabaseConnection
from log import logger


async def bootstrap(metrics_db: DatabaseConnection) -> None:
    config  = _load_config()
    servers = config.get("servers")

    if not servers:
        await logger.info("Bootstrap", "config", "No servers in config.yaml — skipping")
        return

    async with metrics_db as conn:
        for entry in servers:
            try:
                row = await _upsert_server(conn, entry)
                for db_name in entry.get("databases", []):
                    await _upsert_database(conn, row, db_name)

            except psycopg.errors.UniqueViolation:
                continue
                
            except Exception as error:
                await logger.error("Bootstrap", entry.get("name", "?"), f"Failed: {error}")
                continue

        await conn.commit()
