from psycopg.rows import dict_row

from collector.collectors.result import SyncResult
from database import DatabaseConnection, load_monitored_query, load_storage_query
from collector.collectors.base import BaseCollector
from collector.database.registry import MonitoredDatabase
from log import logger


_COLLECT_TABLES = load_monitored_query("tables")
_SELECT_TABLES = load_storage_query(schema="metadata", table="table", query_type="SELECT", query_name="default")
_INSERT_TABLE = load_storage_query(schema="metadata", table="table", query_type="INSERT", query_name="default")
_UPDATE_TABLE = load_storage_query(schema="metadata", table="table", query_type="UPDATE", query_name="default")
_DELETE_TABLE = load_storage_query(schema="metadata", table="table", query_type="UPDATE", query_name="soft_delete")

class TableCollector(BaseCollector):

    def __init__(
        self,
        monitored_db: DatabaseConnection,
        metrics_db: DatabaseConnection,
        db: MonitoredDatabase,
    ) -> None:
        super().__init__(monitored_db=monitored_db, metrics_db=metrics_db)
        self._db_id = db.id
        self._db    = db

    async def _collect(self) -> None:
        await logger.info("TableCollector", "tables", f"Starting (db_id={self._db_id})")

        try:
            live = await self._fetch_live()
            live = [t for t in live if self._db.should_include(t["schema_name"], t["name"])]
            
            stored = await self._fetch_stored()
            result = await self._sync(live, stored)
            await logger.info("TableCollector", "tables", str(result))
        except Exception as error:
            await logger.error("TableCollector", "tables", f"Failed (db_id={self._db_id}): {error}")
            raise

    async def _fetch_live(self) -> list[dict]:
        async with self.monitored_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_COLLECT_TABLES)
                return await cur.fetchall()

    async def _fetch_stored(self) -> list[dict]:
        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_SELECT_TABLES, {"database_id": self._db_id})
                return await cur.fetchall()

    async def _sync(
        self,
        live: list[dict],
        stored: list[dict],
    ) -> SyncResult:
        result = SyncResult()
        stored_map = {r["oid"]: r for r in stored}
        live_oids = {r["table_oid"] for r in live}

        to_insert = [r for r in live if r["table_oid"] not in stored_map]
        to_delete = [oid for oid in stored_map if oid not in live_oids]
        to_update = [
            r for r in live
            if r["table_oid"] in stored_map
            and _table_changed(r, stored_map[r["table_oid"]])
        ]

        for row in to_insert:
            row["database_id"] = self._db_id

        async with self.metrics_db as conn:
            async with conn.cursor() as cur:
                if to_insert:
                    await cur.executemany(_INSERT_TABLE, to_insert)
                    result.inserted = len(to_insert)

                if to_update:
                    await cur.executemany(_UPDATE_TABLE, to_update)
                    result.updated = len(to_update)

                if to_delete:
                    await cur.execute(_DELETE_TABLE, {
                        "removed_oids": to_delete,
                        "database_id": self._db_id,
                    })
                    result.deleted = len(to_delete)

            await conn.commit()

        return result


def _table_changed(live: dict, stored: dict) -> bool:
    return (
        live["schema_name"] != stored["schema_name"]
        or live["name"] != stored["name"]
        or live["description"] != stored["description"]
    )