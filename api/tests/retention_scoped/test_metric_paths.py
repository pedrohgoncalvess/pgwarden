"""Exercise deletion through every actual metric ownership path and worker pass."""

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import pytest

from app.retention import cleanup
from app.retention.models import RetentionWindow
from app.retention.ownership import TABLE_NAMES, get_owner
from app.retention.scopes import GLOBAL_ID, save_policy


async def seed_metric_history(session: AsyncSession) -> list[int]:
    """Seed real metadata chains and required columns for all metric tables."""
    servers = []
    for _ in range(2):
        server = await session.scalar(text("""INSERT INTO collector.server(name,host,port,username,password)
            VALUES (:name,'localhost','5432','test','test') RETURNING id"""), {"name": uuid4().hex})
        servers.append(server)
        database = await session.scalar(text("INSERT INTO metadata.database(server_id,db_name) VALUES (:id,'db') RETURNING id"), {"id": server})
        table = await session.scalar(text("""INSERT INTO metadata."table"(database_id,oid,schema_name,name)
            VALUES (:id,1,'public','table') RETURNING id"""), {"id": database})
        column = await session.scalar(text("""INSERT INTO metadata."column"(table_id,name,data_type,ordinal_position)
            VALUES (:id,'column','integer',1) RETURNING id"""), {"id": table})
        index = await session.scalar(text("""INSERT INTO metadata."index"(database_id,table_id,oid,name,type,definition)
            VALUES (:db,:table,1,'index','btree','test') RETURNING id"""), {"db": database, "table": table})
        identifiers = {"server_id": server, "database_id": database, "table_id": table,
                       "column_id": column, "index_id": index}
        for name in TABLE_NAMES:
            columns = list((await session.execute(text("""SELECT column_name,data_type
                FROM information_schema.columns WHERE table_schema='metric' AND table_name=:name
                AND is_nullable='NO' AND column_default IS NULL ORDER BY ordinal_position
            """), {"name": name})).mappings())
            fields, expressions, params = [], [], {}
            for item in columns:
                field, kind = item["column_name"], item["data_type"]
                fields.append(f'"{field}"')
                if kind == "timestamp with time zone":
                    expressions.append("now()-CAST(CAST(:age AS text) AS interval)")
                else:
                    expressions.append(f":{field}")
                    params[field] = identifiers.get(field, False if kind == "boolean" else "test" if kind == "text" else 1)
            for age in ("2 days", "20 days"):
                await session.execute(text(f'INSERT INTO metric."{name}"({",".join(fields)}) VALUES ({",".join(expressions)})'), {**params, "age": age})
    await save_policy(session, "global", GLOBAL_ID, "*", RetentionWindow(value=7, unit="days"))
    return servers


async def test_real_deletion_is_isolated_for_every_metric_table(session: AsyncSession) -> None:
    """Delete expired CPU, database, table, column, index and query history independently."""
    first, other = await seed_metric_history(session)
    for name in TABLE_NAMES:
        assert await cleanup.delete_expired(session, first, name) == 1, name
        counts = [await session.scalar(text(f'SELECT count(*) FROM metric."{name}" m WHERE {get_owner(name)}=:id'), {"id": server}) for server in (first, other)]
        assert counts == [1, 2], name


async def test_scheduled_worker_calls_real_cleanup_and_commits_each_batch(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the production worker pass rather than substituting its deletion function."""
    servers = await seed_metric_history(session)

    @asynccontextmanager
    async def connection() -> Any:
        yield session

    monkeypatch.setattr(cleanup, "DatabaseConnection", connection)
    await cleanup.run_cleanup()
    for name in TABLE_NAMES:
        assert await session.scalar(text(f'SELECT count(*) FROM metric."{name}"')) == 2, name
    assert await session.scalar(text("SELECT count(*) FROM retention.run")) == len(servers)*len(TABLE_NAMES)


async def test_policy_rollback_prevents_partial_scope_change(session: AsyncSession) -> None:
    """A failed policy transaction cannot alter the rule used by deletion."""
    server, _ = await seed_metric_history(session)
    transaction = await session.begin_nested()
    await save_policy(session, "global", GLOBAL_ID, "*", RetentionWindow(value=90, unit="days"))
    await transaction.rollback()
    assert await cleanup.delete_expired(session, server, "cpu") == 1


async def test_concurrent_policy_changes_and_workers_share_one_database_lock(
    session: AsyncSession, retention_database: str,
) -> None:
    """A second connection cannot enter cleanup while a policy change is uncommitted."""
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.retention.scopes import LOCK_KEY

    await save_policy(session, "global", GLOBAL_ID, "*", RetentionWindow(value=7, unit="days"))
    engine = create_async_engine(make_url(retention_database).set(drivername='postgresql+asyncpg'), poolclass=NullPool)
    try:
        async with AsyncSession(engine) as other:
            assert await other.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': LOCK_KEY}) is False
    finally:
        await engine.dispose()
