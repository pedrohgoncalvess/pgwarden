"""Bounded row cleanup with the same inheritance used by Settings."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retention.ownership import get_keys, get_owner, list_tables
from app.retention.scopes import lock_policies, resolve_policy
from database.connection import DatabaseConnection


async def guard_native_policies(session: AsyncSession) -> None:
    """Fail closed if an unmanaged chunk retention job has been recreated."""
    if await session.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='timescaledb')")):
        conflicts = await session.scalar(text("""
            SELECT count(*) FROM timescaledb_information.jobs
            WHERE hypertable_schema='metric' AND proc_name='policy_retention'
        """))
        if conflicts:
            raise RuntimeError("Native retention jobs conflict with scoped retention; remove them before cleanup")


async def delete_expired(
    session: AsyncSession, server_id: int, name: str, batch_size: int = 1000,
) -> int:
    """Remove at most one batch, retaining every row inside the effective window."""
    if not 1 <= batch_size <= 10000:
        raise ValueError("Cleanup batch size must be between 1 and 10000")
    await lock_policies(session)
    await guard_native_policies(session)
    server = (await session.execute(text("""
        SELECT id,public_id,ingestion_project_id FROM collector.server
        WHERE id=:id FOR SHARE
    """), {"id": server_id})).mappings().one_or_none()
    if not server:
        return 0
    policy = await resolve_policy(session, dict(server), name)
    if not policy or not policy["enabled"]:
        return 0
    keys = await get_keys(session, name)
    quoted = [session.bind.dialect.identifier_preparer.quote(key) for key in keys]
    columns = ",".join(quoted)
    selected = ",".join(f"m.{key}" for key in quoted)
    query = f"""
        WITH expired AS MATERIALIZED (
            SELECT {selected} FROM metric."{name}" m
            WHERE {get_owner(name)}=:server
              AND m.collected_at < now() - CAST(CAST(:duration AS text) AS interval)
            ORDER BY m.collected_at LIMIT :batch
        ), removed AS (
            DELETE FROM metric."{name}" WHERE ({columns}) IN
                (SELECT {columns} FROM expired) RETURNING 1
        ) SELECT count(*) FROM removed
    """
    deleted = int(await session.scalar(text(query), {
        "server": server_id, "duration": policy["retention_interval"], "batch": batch_size,
    }))
    await session.execute(text("""
        INSERT INTO retention.run(table_name,server_id,deleted_rows) VALUES (:name,:server,:count)
        ON CONFLICT(table_name,server_id) DO UPDATE SET
            last_run_at=now(), deleted_rows=EXCLUDED.deleted_rows
    """), {"name": name, "server": server_id, "count": deleted})
    return deleted


async def run_cleanup() -> None:
    """Visit every server and table once per pass with independent transactions."""
    async with DatabaseConnection() as session:
        if not await session.scalar(text("SELECT to_regclass('retention.policy')")):
            return
        tables = await list_tables(session)
        servers = list((await session.execute(text("SELECT id FROM collector.server ORDER BY id"))).scalars())
    for server_id in servers:
        for name in tables:
            try:
                async with DatabaseConnection() as session:
                    await session.execute(text("SET LOCAL statement_timeout='30s'"))
                    await session.execute(text("SET LOCAL lock_timeout='5s'"))
                    await delete_expired(session, server_id, name)
                    await session.commit()
            except Exception:
                logging.exception("Retention cleanup failed for server %s metric.%s", server_id, name)


async def run_retention_worker() -> None:
    """Run cleanup every minute and allow cancellation during application shutdown."""
    while True:
        try:
            await run_cleanup()
        except Exception:
            logging.exception("Retention cleanup pass failed")
        await asyncio.sleep(60)
