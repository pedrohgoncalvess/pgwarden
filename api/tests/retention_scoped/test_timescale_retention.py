"""Verify native-policy migration and compressed deletes when TimescaleDB is available."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.retention.cleanup import delete_expired
from app.retention.models import RetentionWindow
from app.retention.scopes import save_policy


async def test_native_migration_and_compressed_server_isolation() -> None:
    """Migrate native retention, then delete one compressed tenant without touching another."""
    url = os.getenv("RETENTION_TIMESCALE_TEST_DATABASE_URL") or os.getenv("RETENTION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set RETENTION_TIMESCALE_TEST_DATABASE_URL for compressed TimescaleDB tests")
    admin = psycopg.connect(url, autocommit=True)
    if not admin.execute("SELECT 1 FROM pg_available_extensions WHERE name='timescaledb'").fetchone():
        admin.close()
        pytest.skip("TimescaleDB extension is not installed on the integration server")
    database = "pgwarden_ts_retention_" + uuid4().hex
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    target = make_url(url).set(database=database)
    first, second = uuid4(), uuid4()
    engine = None
    try:
        with psycopg.connect(target.render_as_string(hide_password=False), autocommit=True) as conn:
            conn.execute("CREATE EXTENSION timescaledb")
            conn.execute("""CREATE SCHEMA collector; CREATE SCHEMA metric; CREATE SCHEMA ingestion;
                CREATE TABLE ingestion.project(id UUID PRIMARY KEY,name TEXT);
                CREATE TABLE collector.server(id BIGINT PRIMARY KEY,public_id UUID UNIQUE,
                    name TEXT,ingestion_project_id UUID,deleted_at TIMESTAMPTZ);
                CREATE TABLE metric.cpu(collected_at TIMESTAMPTZ NOT NULL,server_id BIGINT NOT NULL,
                    cpu_percent REAL,PRIMARY KEY(collected_at,server_id));
                SELECT create_hypertable('metric.cpu','collected_at');
                ALTER TABLE metric.cpu SET (timescaledb.compress,timescaledb.compress_segmentby='server_id');
            """)
            conn.execute("INSERT INTO collector.server(id,public_id,name) VALUES (1,%s,'first'),(2,%s,'second')", (first, second))
            conn.execute("""INSERT INTO metric.cpu VALUES
                (now()-interval '100 days',1,10),(now()-interval '100 days',2,10);
                SELECT compress_chunk(c) FROM show_chunks('metric.cpu') c;
                SELECT add_retention_policy('metric.cpu',interval '7 days');
            """)
            migration = Path(__file__).resolve().parents[3] / 'migrations/sql/20261104_01_scoped-retention.sql'
            conn.execute(migration.read_text())
            assert conn.execute("SELECT count(*) FROM timescaledb_information.jobs WHERE proc_name='policy_retention' AND hypertable_schema='metric'").fetchone()[0] == 0
            assert conn.execute("SELECT duration FROM retention.policy WHERE table_name='cpu'").fetchone()[0].days == 7
        engine = create_async_engine(target.set(drivername='postgresql+asyncpg'), poolclass=NullPool)
        async with AsyncSession(engine) as session:
            await save_policy(session, 'server', first, '*', RetentionWindow(value=180, unit='days'))
            assert await delete_expired(session, 1, 'cpu') == 0
            assert await delete_expired(session, 2, 'cpu') == 1
            await session.commit()
            assert list((await session.execute(text('SELECT server_id FROM metric.cpu'))).scalars()) == [1]
    finally:
        if engine:
            await engine.dispose()
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
        admin.close()
