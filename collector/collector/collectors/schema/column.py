from psycopg.rows import dict_row

from collector.collectors.result import SyncResult
from database import DatabaseConnection, load_monitored_query, load_storage_query
from collector.collectors.base import BaseCollector
from collector.database.registry import MonitoredDatabase
from log import logger


_COLLECT_COLUMNS = load_monitored_query("columns")
_SELECT_COLUMNS = load_storage_query(schema="metadata", table="column", query_type="SELECT", query_name="with_table_metadata")
_INSERT_COLUMN = load_storage_query(schema="metadata", table="column", query_type="INSERT", query_name="default")
_UPDATE_COLUMN = load_storage_query(schema="metadata", table="column", query_type="UPDATE", query_name="default")
_DELETE_COLUMN = load_storage_query(schema="metadata", table="column", query_type="UPDATE", query_name="soft_delete")

class ColumnCollector(BaseCollector):

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
        await logger.info("ColumnCollector", "columns", f"Starting (db_id={self._db_id})")

        try:
            live = await self._fetch_live()
            live = [c for c in live if self._db.should_include(c["schema_name"], c["table_name"])]

            stored = await self._fetch_stored()
            result = await self._sync(live, stored)
            await logger.info("ColumnCollector", "columns", str(result))
        except Exception as error:
            await logger.error("ColumnCollector", "columns", f"Failed (db_id={self._db_id}): {error}")
            raise

    async def _fetch_live(self) -> list[dict]:
        async with self.monitored_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_COLLECT_COLUMNS)
                return await cur.fetchall()

    async def _fetch_stored(self) -> list[dict]:
        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_SELECT_COLUMNS, {"database_id": self._db_id})
                return await cur.fetchall()

    async def _sync(
        self,
        live: list[dict],
        stored: list[dict],
    ) -> SyncResult:
        result = SyncResult()

        stored_map = {(r["table_oid"], r["name"]): r for r in stored}
        live_keys = {(r["table_oid"], r["name"]) for r in live}

        to_insert = [
            r for r in live
            if (r["table_oid"], r["name"]) not in stored_map
        ]

        to_delete_ids = [
            stored_map[key]["id"]
            for key in stored_map
            if key not in live_keys
        ]

        to_update = [
            r for r in live
            if (r["table_oid"], r["name"]) in stored_map
            and _column_changed(r, stored_map[(r["table_oid"], r["name"])])
        ]

        oid_to_id = await self._fetch_oid_map()

        for row in to_insert:
            row["table_id"] = oid_to_id.get(row["table_oid"])
            row["fk_table_id"] = _resolve_fk_table(row, oid_to_id)
            row.setdefault("fk_column_id", None)

        for row in to_update:
            row["table_id"] = oid_to_id.get(row["table_oid"])
            row["fk_table_id"] = _resolve_fk_table(row, oid_to_id)
            row.setdefault("fk_column_id", None)

        async with self.metrics_db as conn:
            async with conn.cursor() as cur:
                if to_insert:
                    await cur.executemany(_INSERT_COLUMN, to_insert)
                    result.inserted = len(to_insert)

                if to_update:
                    await cur.executemany(_UPDATE_COLUMN, to_update)
                    result.updated = len(to_update)

                if to_delete_ids:
                    await cur.execute(
                        _DELETE_COLUMN,
                        {"removed_ids": to_delete_ids},
                    )
                    result.deleted = len(to_delete_ids)

            await conn.commit()

        return result

    async def _fetch_oid_map(self) -> dict[int, int]:
        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    load_storage_query(schema="metadata", table="table", query_type="SELECT", query_name="by_database_id_and_active"),
                    {"database_id": self._db_id}
                )
                rows = await cur.fetchall()
                return {r["oid"]: r["id"] for r in rows}


def _column_changed(live: dict, stored: dict) -> bool:
    fields = [
        "name",
        "data_type",
        "is_nullable",
        "default_value",
        "is_unique",
        "ordinal_position",
        "description",
        "foreign_table_oid"
    ]

    for field in fields:
        live_val = live.get(field)
        stored_val = stored.get(field)
        if live_val != stored_val:
            return True

    return False


def _resolve_fk_table(row: dict, oid_to_id: dict[int, int]) -> int | None:
    fk_oid = row.get("foreign_table_oid")
    return oid_to_id.get(fk_oid) if fk_oid else None