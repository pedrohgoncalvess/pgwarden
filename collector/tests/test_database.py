"""
Connection smoke test for the collector (psycopg + connection pool).

Adapted to the collector's psycopg-based DatabaseConnection, which differs
from the SQLAlchemy modules by design. Requires a reachable PostgreSQL
instance and the DB_* environment variables to be set.
"""
import pytest

from database.connection import DatabaseConnection


@pytest.mark.asyncio
async def test_successful_connection():
    conn = DatabaseConnection()

    async with conn as connection:
        assert connection is not None

        async with connection.cursor() as cur:
            await cur.execute("SELECT 1 AS one")
            row = await cur.fetchone()
            assert row["one"] == 1

    await DatabaseConnection.shutdown()
