"""Isolate real PostgreSQL retention tests from the application's shared test DB."""

import os
import re
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import pytest_asyncio
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool


os.environ.setdefault("JWT_SECRET_KEY", "retention-tests-only-secret-with-32-bytes")
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def retention_database() -> Iterator[str]:
    """Create a disposable DB using actual metric and scoped-retention migrations."""
    url = os.getenv("RETENTION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set RETENTION_TEST_DATABASE_URL to run real PostgreSQL deletion tests")
    database = "pgwarden_retention_" + uuid4().hex
    admin = psycopg.connect(url, autocommit=True)
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    target = make_url(url).set(database=database).render_as_string(hide_password=False)
    try:
        with psycopg.connect(target, autocommit=True) as connection:
            for filename in (
                "20260324_01_pUn2z.sql", "20260424_01_9UN1w-add-n-mod-since-analyze.sql",
                "20260623_01_database-stats-metric.sql", "20260624_01_native-query-metric.sql",
                "20260709_01_zo2AJ-analytics-module.sql", "20261031_02_index-advisor.sql",
                "20261101_01_query-sources.sql", "20261030_01_ingestion-projects.sql",
                "20261104_01_scoped-retention.sql",
            ):
                ddl = (ROOT / "migrations/sql" / filename).read_text()
                ddl = re.sub(r"CREATE EXTENSION IF NOT EXISTS (timescaledb|vector);", "", ddl)
                ddl = re.sub(r"SELECT create_hypertable\([^;]+;", "", ddl)
                connection.execute(ddl)
        yield target
    finally:
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
        admin.close()


@pytest_asyncio.fixture
async def session(retention_database: str) -> AsyncIterator[AsyncSession]:
    """Roll back every test while allowing independent real SQL transactions."""
    engine = create_async_engine(make_url(retention_database).set(drivername="postgresql+asyncpg"), poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        await transaction.rollback()
    await engine.dispose()
