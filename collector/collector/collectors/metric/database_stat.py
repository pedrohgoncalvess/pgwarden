from datetime import datetime, timezone

from psycopg.rows import dict_row

from database import (
    DatabaseConnection, load_monitored_query,
    load_storage_query
)
from collector.collectors.base import BaseCollector
from collector.collectors.result import SyncResult
from log import logger


def _align_collected_at() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(second=0, microsecond=0)


_COLLECT_DATABASE_STATS = load_monitored_query("database_stats")
_INSERT_DATABASE_STAT = load_storage_query(schema="metric", table="database_stat", query_type="INSERT", query_name="default")
_SELECT_TRACKED_DB = load_storage_query(schema="metadata", table="database", query_type="SELECT", query_name="by_id")

class DatabaseStatCollector(BaseCollector):
    def __init__(self, monitored_db: DatabaseConnection, metrics_db: DatabaseConnection, db_id: int) -> None:
        super().__init__(monitored_db=monitored_db, metrics_db=metrics_db)
        self._db_id = db_id

    async def _collect(self) -> SyncResult:
        result = SyncResult()
        try:
            db_info = await self._fetch_db_info()
            if not db_info:
                return result

            collected_at = _align_collected_at()

            async with self.monitored_db as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(_COLLECT_DATABASE_STATS, {"database_oid": db_info["oid"]})
                    stats = await cur.fetchone()

            if not stats:
                await logger.info("DatabaseStatCollector", "database_stats", f"No stats found for db_id={self._db_id}")
                return result

            to_insert = {
                "collected_at": collected_at,
                "database_id": self._db_id,
                "xact_commit": stats["xact_commit"],
                "xact_rollback": stats["xact_rollback"],
                "blks_read": stats["blks_read"],
                "blks_hit": stats["blks_hit"],
                "tup_returned": stats["tup_returned"],
                "tup_fetched": stats["tup_fetched"],
                "tup_inserted": stats["tup_inserted"],
                "tup_updated": stats["tup_updated"],
                "tup_deleted": stats["tup_deleted"],
                "conflicts": stats["conflicts"],
                "deadlocks": stats["deadlocks"],
                "db_size_bytes": stats["db_size_bytes"],
            }

            async with self.metrics_db as conn:
                async with conn.cursor() as cur:
                    await cur.execute(_INSERT_DATABASE_STAT, to_insert)
                await conn.commit()

            result.inserted = 1
            await logger.info("DatabaseStatCollector", "database_stats", f"Collected 1 database stat row (db_id={self._db_id})")
        except Exception as error:
            await logger.error("DatabaseStatCollector", "database_stats", f"Failed (db_id={self._db_id}): {error}")
            raise

        return result

    async def _fetch_db_info(self) -> dict | None:
        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_SELECT_TRACKED_DB, {"database_id": self._db_id})
                return await cur.fetchone()
