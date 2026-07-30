import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from analytics.utils import get_env_var


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class DatabaseConnection:
    """Standard async PostgreSQL (SQLAlchemy + asyncpg) connection.

    Two equivalent usage patterns:

        async with DatabaseConnection() as session:
            ...

        async with DatabaseConnection().connect() as session:
            ...
    """

    _engine: AsyncEngine | None = None
    _session_maker: async_sessionmaker[AsyncSession] | None = None
    _engine_lock: asyncio.Lock | None = None

    def __init__(self) -> None:
        host = get_env_var("DB_HOST")
        port = get_env_var("DB_PORT")
        user = get_env_var("DB_USER")
        password = get_env_var("DB_PASSWORD")
        db_name = get_env_var("DB_NAME")
        self._database_url = (
            f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"
        )
        self._ctx = None

    @classmethod
    async def _get_session_maker(
        cls, database_url: str
    ) -> async_sessionmaker[AsyncSession]:
        if cls._session_maker is not None:
            return cls._session_maker
        if cls._engine_lock is None:
            cls._engine_lock = asyncio.Lock()

        async with cls._engine_lock:
            if cls._session_maker is None:
                cls._engine = create_async_engine(
                    database_url,
                    echo=False,
                    future=True,
                    pool_size=5,
                    max_overflow=0,
                    pool_timeout=30,
                    pool_pre_ping=True,
                    connect_args={"server_settings": {"application_name": "pgwarden_analytics"}},
                )
                cls._session_maker = async_sessionmaker(
                    bind=cls._engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
        return cls._session_maker

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncSession]:
        """Yield a fresh session that is automatically closed on exit."""
        session = (await self._get_session_maker(self._database_url))()
        try:
            yield session
        finally:
            await session.close()

    @classmethod
    async def shutdown(cls) -> None:
        """Dispose the shared engine and release its pooled connections."""
        if cls._engine is not None:
            await cls._engine.dispose()
        cls._engine = None
        cls._session_maker = None
        cls._engine_lock = None

    async def close(self) -> None:
        """Dispose the shared engine and release its pooled connections."""
        await self.shutdown()

    async def __aenter__(self) -> AsyncSession:
        self._ctx = self.connect()
        return await self._ctx.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._ctx.__aexit__(exc_type, exc_val, exc_tb)
