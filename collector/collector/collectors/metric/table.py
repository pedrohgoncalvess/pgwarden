from datetime import datetime, timezone

from psycopg.rows import dict_row

from database import (
    DatabaseConnection, load_monitored_query,
    load_storage_query
)
from collector.collectors.base import BaseCollector
from collector.collectors.result import SyncResult
from log import logger


_COLLECT_TABLE_METRICS = load_monitored_query("tables_detail")
_INSERT_TABLE_METRIC = load_storage_query(schema="metric", table="table", query_type="INSERT", query_name="default")
_SELECT_TRACKED_TABLE = load_storage_query(schema="metadata", table="table", query_type="SELECT", query_name="by_database_id_and_active")

class TableMetricCollector(BaseCollector):

    def __init__(
        self,
        monitored_db: DatabaseConnection,
        metrics_db: DatabaseConnection,
        db_id: int,
    ) -> None:
        super().__init__(monitored_db=monitored_db, metrics_db=metrics_db)
        self._db_id = db_id

    async def _collect(self) -> SyncResult:
        await logger.info("TableMetricCollector", "tables", f"Starting (db_id={self._db_id})")
        result = SyncResult()

        try:
            tbl_map, tbl_oids = await self._fetch_table_mapping()

            if not tbl_oids:
                await logger.info("TableMetricCollector", "tables", "No tracked tables. Skipping.")
                return result

            collected_at = datetime.now(timezone.utc)
            tbl_metrics = []

            async with self.monitored_db as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(_COLLECT_TABLE_METRICS, {"table_oids": list(tbl_oids)})
                    tbl_metrics = await cur.fetchall()

            to_insert = []
            for row in tbl_metrics:
                tbl_id = tbl_map.get(row["table_oid"])
                if tbl_id:
                    to_insert.append({
                        "collected_at": collected_at,
                        "table_id": tbl_id,
                        "n_live_tup": row["n_live_tup"],
                        "n_dead_tup": row["n_dead_tup"],
                        "table_size_bytes": row["table_size_bytes"],
                        "last_vacuum": row["last_vacuum"],
                        "last_autovacuum": row["last_autovacuum"],
                        "last_analyze": row["last_analyze"],
                        "last_autoanalyze": row["last_autoanalyze"],
                        "seq_scan": row["seq_scan"],
                        "idx_scan": row["idx_scan"],
                        "modifications_since_last_analyze": row["n_mod_since_analyze"],
                        "heap_blks_read": row["heap_blks_read"],
                        "heap_blks_hit": row["heap_blks_hit"]
                    })

            async with self.metrics_db as conn:
                async with conn.cursor() as cur:
                    if to_insert:
                        await cur.executemany(_INSERT_TABLE_METRIC, to_insert)
                await conn.commit()

            result.inserted = len(to_insert)
            await logger.info("TableMetricCollector", "tables", str(result))

        except Exception as error:
            await logger.error("TableMetricCollector", "tables", f"Failed (db_id={self._db_id}): {error}")
            raise

        return result

    async def _fetch_table_mapping(self) -> tuple[dict[int, int], set[int]]:
        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_SELECT_TRACKED_TABLE, {"database_id": self._db_id})
                rows = await cur.fetchall()
                mapping = {r["oid"]: r["id"] for r in rows}
                oids = {r["oid"] for r in rows}
                return mapping, oids