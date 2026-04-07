import re
from dataclasses import dataclass

from psycopg.rows import dict_row

from database import DatabaseConnection, load_monitored_query, load_storage_query
from utils import decrypt
from log import logger


_SELECT_DATABASES = load_storage_query(schema="metadata", table="database", query_type="SELECT", query_name="default")
_UPDATE_LAST_SEEN = load_storage_query(schema="metadata", table="database", query_type="UPDATE", query_name="last_seen")

@dataclass
class MonitoredDatabase:
    id:              int
    server_id:       int
    name:            str
    conninfo:        str
    ignore_pattern:  str | None = None
    ignore_tables:   list[str] | None = None
    include_tables:  list[str] | None = None

    def should_include(self, schema_name: str, table_name: str) -> bool:
        full_name = f"{schema_name}.{table_name}"

        # 1. ignore_tables (highest priority)
        if self.ignore_tables:
            normalized_ignore = [(t if "." in t else f"public.{t}") for t in self.ignore_tables]
            if full_name in normalized_ignore:
                return False

        # 2. ignore_pattern
        if self.ignore_pattern and re.search(self.ignore_pattern, full_name, re.IGNORECASE):
            return False

        # 3. include_tables (lowest priority / restrictive allow-list)
        if self.include_tables:
            normalized_include = [(t if "." in t else f"public.{t}") for t in self.include_tables]
            return full_name in normalized_include

        return True


class DatabaseRegistry:

    POLL_INTERVAL = 30.0

    def __init__(self, metrics_db: DatabaseConnection) -> None:
        self._metrics_db = metrics_db
        self._databases: dict[int, MonitoredDatabase] = {}

    async def sync(self) -> None:
        async with self._metrics_db as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_SELECT_DATABASES)
                rows = await cur.fetchall()

        fresh: dict[int, MonitoredDatabase] = {}

        for row in rows:
            try:
                host     = decrypt(row["host"])
                port     = decrypt(row["port"])
                username = decrypt(row["username"])
                password = decrypt(row["password"])
                db_name  = decrypt(row["db_name"])
            except Exception as error:
                await logger.error(
                    "DatabaseRegistry",
                    row["name"],
                    f"Failed to decrypt credentials: {error}",
                )
                continue

            label   = f"{row['name']}/{db_name}"
            conninfo = (
                f"host={host} "
                f"port={port} "
                f"dbname={db_name} "
                f"user={username} "
                f"password={password} "
                f"sslmode={row['ssl_mode']} "
                f"options='-c statement_timeout=5000 "
                f"-c lock_timeout=1000 "
                f"-c application_name=pgwarden_collector'"
            )

            if row["oid"] is None:
                await self._populate_oid(row["id"], conninfo, label)

            fresh[row["id"]] = MonitoredDatabase(
                id=row["id"],
                server_id=row["server_id"],
                name=label,
                conninfo=conninfo,
                ignore_pattern=row.get("ignore_pattern"),
                ignore_tables=row.get("ignore_tables"),
                include_tables=row.get("include_tables"),
            )

        added   = set(fresh) - set(self._databases)
        removed = set(self._databases) - set(fresh)

        if added:
            await logger.info("DatabaseRegistry", "sync", f"Added: {[fresh[i].name for i in added]}")
        if removed:
            await logger.info("DatabaseRegistry", "sync", f"Removed: {[self._databases[i].name for i in removed]}")

        self._databases = fresh

    async def _populate_oid(self, db_id: int, conninfo: str, label: str) -> None:
        try:
            monitored = DatabaseConnection(conninfo=conninfo)
            async with monitored as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        load_monitored_query(query_type="database")
                    )
                    result = await cur.fetchone()

            if not result:
                return

            async with self._metrics_db as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        load_storage_query(schema="metadata", table="database", query_type="UPDATE", query_name="set_oid"),
                        {"database_id": result["oid"], "id": db_id}
                    )
                await conn.commit()

            await logger.info("DatabaseRegistry", label, f"database_oid populated: {result['oid']}")

        except Exception as error:
            await logger.error("DatabaseRegistry", label, f"Failed to populate database_oid: {error}")

    async def update_last_seen(self, db_id: int, error: str | None = None) -> None:
        async with self._metrics_db as conn:
            async with conn.cursor() as cur:
                await cur.execute(_UPDATE_LAST_SEEN, {"id": db_id, "error": error})
            await conn.commit()

    def all(self) -> list[MonitoredDatabase]:
        return list(self._databases.values())

    def get(self, db_id: int) -> MonitoredDatabase | None:
        return self._databases.get(db_id)