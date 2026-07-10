import pytest
from sqlalchemy import text

from database import DatabaseConnection


@pytest.mark.asyncio
async def test_successful_connection():
    conn = DatabaseConnection()

    async with conn as session:
        assert session is not None
        assert session.bind is not None

        result = await session.execute(text("SELECT 1"))
        value = result.scalar()
        assert value == 1
