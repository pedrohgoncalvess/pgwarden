from datetime import datetime, timezone

from psycopg.rows import dict_row

from database import (
    DatabaseConnection, load_monitored_query,
    load_storage_query
)
from collector.collectors.base import BaseCollector
from collector.collectors.result import SyncResult
from log import logger


_COLLECT_NATIVE_QUERIES = load_monitored_query("native_queries")
_INSERT_NATIVE_QUERY = load_storage_query(schema="metric", table="native_query", query_type="INSERT", query_name="default")
_SELECT_TRACKED_DB = load_storage_query(schema="metadata", table="database", query_type="SELECT", query_name="by_id")


class NativeQueryMetricCollector(BaseCollector):
    def __init__(self, monitored_db: DatabaseConnection, metrics_db: DatabaseConnection, db_id: int) -> None:
        super().__init__(monitored_db=monitored_db, metrics_db=metrics_db)
        self._db_id = db_id

    async def _collect(self) -> SyncResult:
        result = SyncResult()
        try:
            db_info = await self._fetch_db_info()
            if not db_info:
                return result

            collected_at = datetime.now(timezone.utc)
            to_insert = []

            async with self.monitored_db as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(_COLLECT_NATIVE_QUERIES, {"database_oid": db_info["oid"]})
                    rows = await cur.fetchall()

            for row in rows:
                to_insert.append({
                    "collected_at": collected_at,
                    "database_id": self._db_id,
                    "pid": row["pid"],
                    "leader_pid": row["leader_pid"],
                    "usesysid": row["usesysid"],
                    "user_name": row["user_name"],
                    "application_name": row["application_name"],
                    "client_addr": row["client_addr"],
                    "client_hostname": row["client_hostname"],
                    "client_port": row["client_port"],
                    "backend_start": row["backend_start"],
                    "xact_start": row["xact_start"],
                    "query_start": row["query_start"],
                    "state_change": row["state_change"],
                    "wait_event_type": row["wait_event_type"],
                    "wait_event": row["wait_event"],
                    "state": row["state"],
                    "backend_xid": row["backend_xid"],
                    "backend_xmin": row["backend_xmin"],
                    "query_id": row["query_id"],
                    "backend_type": row["backend_type"],
                    "query": row["query"],
                    "query_hash": row["query_hash"],
                    "query_duration_ms": row["query_duration_ms"],
                    "transaction_duration_ms": row["transaction_duration_ms"],
                    "backend_duration_ms": row["backend_duration_ms"],
                })

            if to_insert:
                async with self.metrics_db as conn:
                    async with conn.cursor() as cur:
                        await cur.executemany(_INSERT_NATIVE_QUERY, to_insert)
                    await conn.commit()

            result.inserted = len(to_insert)
            await logger.info(
                "NativeQueryMetricCollector",
                "native_query",
                f"Collected {result.inserted} native query rows (db_id={self._db_id})",
            )
        except Exception as error:
            await logger.error("NativeQueryMetricCollector", "native_query", f"Failed (db_id={self._db_id}): {error}")
            raise

        return result

    async def _fetch_db_info(self) -> dict | None:
        async with self.metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_SELECT_TRACKED_DB, {"database_id": self._db_id})
                return await cur.fetchone()
