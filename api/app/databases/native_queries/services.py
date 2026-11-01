import asyncio
import json
from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, desc

from database.connection import DatabaseConnection
from database.models.collector.server import Server
from database.models.metadata.database import Database
from database.models.metric.native_query import NativeQueryMetric
from utils import decrypt, decrypt_or_plain


_LIVE_NATIVE_QUERY_SQL = """
SELECT
    clock_timestamp() AS collected_at,
    pid,
    leader_pid,
    usesysid,
    usename AS user_name,
    application_name,
    client_addr::text AS client_addr,
    client_hostname,
    client_port,
    backend_start,
    xact_start,
    query_start,
    state_change,
    wait_event_type,
    wait_event,
    state,
    backend_xid::text AS backend_xid,
    backend_xmin::text AS backend_xmin,
    query_id,
    backend_type,
    query,
    md5(query) AS query_hash,
    CASE
        WHEN query_start IS NULL THEN NULL
        ELSE (EXTRACT(EPOCH FROM (clock_timestamp() - query_start)) * 1000)::double precision
    END AS query_duration_ms,
    CASE
        WHEN xact_start IS NULL THEN NULL
        ELSE (EXTRACT(EPOCH FROM (clock_timestamp() - xact_start)) * 1000)::double precision
    END AS transaction_duration_ms,
    CASE
        WHEN backend_start IS NULL THEN NULL
        ELSE (EXTRACT(EPOCH FROM (clock_timestamp() - backend_start)) * 1000)::double precision
    END AS backend_duration_ms
FROM pg_stat_activity
WHERE datid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND pid <> pg_backend_pid()
"""


def serialize_row(row) -> dict:
    return jsonable_encoder({
        key: value for key, value in row.__dict__.items() if not key.startswith("_")
    })


def serialize_record(record) -> dict:
    data = {}
    for key, value in dict(record).items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        else:
            data[key] = value
    return data


async def get_monitored_connection_settings(database_id: UUID) -> dict | None:
    async with DatabaseConnection() as conn:
        db_result = await conn.execute(
            select(Database).where(Database.public_id == database_id)
        )
        database = db_result.scalar_one_or_none()
        if database is None:
            return None

        server_result = await conn.execute(
            select(Server).where(Server.id == database.server_id)
        )
        server = server_result.scalar_one_or_none()
        if server is None:
            return None

        # Remote collectors intentionally do not send connection credentials.
        # Their query samples are already available in the central store.
        if server.ingestion_project_id is not None:
            return {"snapshot_database_id": database.id}

        return {
            "host": decrypt(server.host),
            "port": int(decrypt(server.port)),
            "user": decrypt(server.username),
            "password": decrypt(server.password),
            "database": decrypt_or_plain(database.db_name),
            "ssl": "prefer" if server.ssl_mode == "prefer" else server.ssl_mode,
        }


async def stored_native_query_stream(database_id: int):
    while True:
        try:
            async with DatabaseConnection() as conn:
                result = await conn.execute(
                    select(NativeQueryMetric.collected_at)
                    .where(NativeQueryMetric.database_id == database_id)
                    .order_by(desc(NativeQueryMetric.collected_at))
                    .limit(1)
                )
                latest = result.scalar_one_or_none()
                payload = []
                if latest is not None:
                    result = await conn.execute(
                        select(NativeQueryMetric)
                        .where(
                            NativeQueryMetric.database_id == database_id,
                            NativeQueryMetric.collected_at == latest,
                        )
                        .order_by(NativeQueryMetric.pid, NativeQueryMetric.backend_start)
                    )
                    payload = [serialize_row(row) for row in result.scalars().all()]

            # Yield after releasing the pooled connection: protect_stream needs
            # its own session to recheck access before delivering the snapshot.
            yield {"event": "native_query", "data": json.dumps(payload)}
        except Exception as error:
            yield {"event": "error", "data": json.dumps({"error": str(error)})}

        await asyncio.sleep(2)


async def native_query_stream(database_id: UUID):
    settings = await get_monitored_connection_settings(database_id)
    if settings is None:
        yield {"event": "error", "data": json.dumps({"error": "Database not found"})}
        return

    if "snapshot_database_id" in settings:
        source = stored_native_query_stream(settings["snapshot_database_id"])
        try:
            async for event in source:
                yield event
        finally:
            await source.aclose()
        return

    monitored_conn = None

    try:
        while True:
            try:
                if monitored_conn is None or monitored_conn.is_closed():
                    monitored_conn = await asyncpg.connect(**settings, timeout=5)

                rows = await monitored_conn.fetch(_LIVE_NATIVE_QUERY_SQL)
                payload = [serialize_record(row) for row in rows]
                yield {"event": "native_query", "data": json.dumps(payload)}

            except Exception as e:
                if monitored_conn is not None and not monitored_conn.is_closed():
                    await monitored_conn.close()
                monitored_conn = None
                yield {"event": "error", "data": json.dumps({"error": str(e)})}

            await asyncio.sleep(0.5)
    finally:
        if monitored_conn is not None and not monitored_conn.is_closed():
            await monitored_conn.close()


async def list_native_queries(database_id: UUID, limit: int = 100) -> list[dict]:
    async with DatabaseConnection() as conn:
        db_result = await conn.execute(
            select(Database.id).where(Database.public_id == database_id)
        )
        internal_database_id = db_result.scalar_one_or_none()
        if internal_database_id is None:
            return []

        rows_result = await conn.execute(
            select(NativeQueryMetric)
            .where(NativeQueryMetric.database_id == internal_database_id)
            .order_by(desc(NativeQueryMetric.collected_at))
            .limit(limit)
        )
        return [serialize_row(row) for row in rows_result.scalars().all()]
