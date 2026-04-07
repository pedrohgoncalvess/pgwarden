import json

from psycopg.rows import dict_row

from collector.collectors.result import SyncResult
from database import DatabaseConnection, load_monitored_query, load_storage_query
from collector.collectors.base import BaseCollector
from collector.database.registry import MonitoredDatabase
from log import logger


_COLLECT_INDEXES = load_monitored_query("indexes")
_SELECT_INDEXES = load_storage_query(schema="metadata", table="index", query_type="SELECT", query_name="with_columns_json")
_INSERT_INDEX = load_storage_query(schema="metadata", table="index", query_type="INSERT", query_name="default")
_UPDATE_INDEX = load_storage_query(schema="metadata", table="index", query_type="UPDATE", query_name="default")
_DELETE_INDEX = load_storage_query(schema="metadata", table="index", query_type="UPDATE", query_name="soft_delete")
_SELECT_INDEX_BY_OID = load_storage_query(schema="metadata", table="index", query_type="SELECT", query_name="by_oid")
_INSERT_INDEX_COLUMN = load_storage_query(schema="metadata", table="index_column", query_type="INSERT", query_name="default")
_DELETE_INDEX_COLUMNS = load_storage_query(schema="metadata", table="index_column", query_type="DELETE", query_name="by_index_id")

class IndexCollector(BaseCollector):

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
        await logger.info("IndexCollector", "indexes", f"Starting (db_id={self._db_id})")

        try:
            live = await self._fetch_live()
            live = [i for i in live if self._db.should_include(i["schema_name"], i["table_name"])]

            stored = await self._fetch_stored()
            result = await self._sync(live, stored)
            await logger.info("IndexCollector", "indexes", str(result))
        except Exception as error:
            await logger.error("IndexCollector", "indexes", f"Failed (db_id={self._db_id}): {error}")
            raise

    async def _fetch_live(self) -> list[dict]:
        async with self.monitored_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_COLLECT_INDEXES)
                return await cur.fetchall()

    async def _fetch_stored(self) -> list[dict]:
        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_SELECT_INDEXES, {"database_id": self._db_id})
                return await cur.fetchall()

    async def _sync(
        self,
        live: list[dict],
        stored: list[dict],
    ) -> SyncResult:
        result = SyncResult()

        stored_map = {r["oid"]: r for r in stored}
        live_oids = {r["index_oid"] for r in live}

        to_insert = [r for r in live if r["index_oid"] not in stored_map]
        to_delete = [oid for oid in stored_map if oid not in live_oids]
        to_update = [
            r for r in live
            if r["index_oid"] in stored_map
            and _index_changed(r, stored_map[r["index_oid"]])
        ]

        table_oid_to_id = await self._fetch_table_oid_map()
        col_attnum_to_id = await self._fetch_column_attnum_map()

        for row in to_insert:
            row["database_id"] = self._db_id
            table_id = table_oid_to_id.get(row["table_oid"])

            if table_id:
                row["table_id"] = table_id
            else:
                continue

        for row in to_update:
            row["table_id"] = table_oid_to_id.get(row["table_oid"])

        index_oid_to_id_map = {}

        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                if to_delete:
                    await cur.execute(_DELETE_INDEX, {
                        "removed_oids": to_delete,
                        "database_id": self._db_id,
                    })
                    result.deleted = len(to_delete)

                if to_insert:
                    await cur.executemany(_INSERT_INDEX, to_insert)
                    result.inserted = len(to_insert)

                    inserted_oids = [r["index_oid"] for r in to_insert]
                    await cur.execute(
                        _SELECT_INDEX_BY_OID,
                        {"oids": inserted_oids}
                    )
                    for row in await cur.fetchall():
                        index_oid_to_id_map[row["oid"]] = row["id"]

                if to_update:
                    await cur.executemany(_UPDATE_INDEX, to_update)

                    updated_oids = [r["index_oid"] for r in to_update]
                    await cur.execute(
                        _SELECT_INDEX_BY_OID,
                        {"oids": updated_oids}
                    )
                    for row in await cur.fetchall():
                        index_oid_to_id_map[row["oid"]] = row["id"]

                    result.updated = len(to_update)

                indices_to_sync = to_insert + to_update
                if indices_to_sync:
                    sync_ids = [index_oid_to_id_map[r["index_oid"]] for r in indices_to_sync]

                    await cur.execute(
                        _DELETE_INDEX_COLUMNS,
                        {"ids": sync_ids}
                    )

                    rel_rows = []
                    for idx_data in indices_to_sync:
                        idx_id = index_oid_to_id_map[idx_data["index_oid"]]
                        table_oid = idx_data["table_oid"]

                        cols_info = (
                            json.loads(idx_data["columns_info"])
                            if isinstance(idx_data["columns_info"], str)
                            else idx_data["columns_info"]
                        )

                        for col in cols_info:
                            col_id = col_attnum_to_id.get((table_oid, col["column_attnum"]))
                            if col_id:
                                rel_rows.append({
                                    "index_id": idx_id,
                                    "column_id": col_id,
                                    "ordinal_position": col["ordinal"]
                                })

                    if rel_rows:
                        await cur.executemany(_INSERT_INDEX_COLUMN, rel_rows)

            await conn.commit()

        return result

    async def _fetch_table_oid_map(self) -> dict[int, int]:
        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    load_storage_query(schema="metadata", table="table", query_type="SELECT", query_name="by_database_id_and_active"),
                    {"database_id": self._db_id}
                )
                rows = await cur.fetchall()
                return {r["oid"]: r["id"] for r in rows}

    async def _fetch_column_attnum_map(self) -> dict[tuple[int, int], int]:
        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT t.oid AS table_oid, c.ordinal_position AS attnum, c.id
                    FROM metadata.column c
                    JOIN metadata.table t ON t.id = c.table_id
                    WHERE t.database_id = %s AND c.deleted_at IS NULL
                """, (self._db_id,))
                rows = await cur.fetchall()
                return {(r["table_oid"], r["attnum"]): r["id"] for r in rows}


def _index_changed(live: dict, stored: dict) -> bool:
    fields = [
        "name",
        "type",
        "definition",
        "is_unique",
        "is_primary",
        "columns_info"
    ]

    for field in fields:
        live_val = live.get(field)
        stored_val = stored.get(field)

        if field == "name" and "index_name" in live: live_val = live["index_name"]
        if field == "type" and "index_type" in live: live_val = live["index_type"]

        if json.dumps(live_val, sort_keys=True) != json.dumps(stored_val, sort_keys=True):
            return True

    return False