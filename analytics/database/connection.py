import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from analytics.utils import get_env_var


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class DatabaseConnection:
    """Standard async PostgreSQL (SQLAlchemy + asyncpg) connection.

    Two equivalent usage patterns:

        async with DatabaseConnection() as session:            # __aenter__/__aexit__
            ...

        async with DatabaseConnection().connect() as session:  # async context manager
            ...
    """

    def __init__(self) -> None:
        host = get_env_var("DB_HOST")
        port = get_env_var("DB_PORT")
        user = get_env_var("DB_USER")
        password = get_env_var("DB_PASSWORD")
        db_name = get_env_var("DB_NAME")
        self._database_url = (
            f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"
        )
        self._engine = None
        self._session_maker = None
        self._ctx = None

    def _ensure_engine(self) -> None:
        if not self._engine:
            self._engine = create_async_engine(
                self._database_url,
                echo=False,
                future=True,
            )
            self._session_maker = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncSession]:
        """Yield a fresh session that is automatically closed on exit."""
        self._ensure_engine()
        session = self._session_maker()
        try:
            yield session
        finally:
            await session.close()

    async def close(self) -> None:
        """Dispose the engine and release all pooled connections."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None

    async def __aenter__(self) -> AsyncSession:
        self._ctx = self.connect()
        return await self._ctx.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._ctx.__aexit__(exc_type, exc_val, exc_tb)
