"""Initial schema synchronization shared by both storage backends."""

from collector.collectors import TableCollector, ColumnCollector, IndexCollector
from database import DatabaseConnection, MonitoredDatabase
from database.storage import StorageConnection
from log import logger


async def run_startup_collectors(
    monitored_db: DatabaseConnection,
    metrics_db: StorageConnection,
    db: MonitoredDatabase,
) -> None:
    """Synchronize target schemas before starting metric collection."""
    await logger.info(
        "Main", "startup_sync", f"Running initial schema sync (db_id={db.id})"
    )

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
            await logger.error(
                "Main", "startup_sync", f"{name} failed on startup: {error}"
            )
            raise
