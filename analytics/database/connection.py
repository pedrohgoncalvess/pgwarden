import asyncio
import sys
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from analytics.utils import get_env_var


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class DatabaseConnection:
    def __init__(self):
        host = get_env_var("DB_HOST")
        port = get_env_var("DB_PORT")
        user = get_env_var("DB_USER")
        password = get_env_var("DB_PASSWORD")
        db_name = get_env_var("DB_NAME")
        self._database_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"
        self._engine = None
        self._session_maker = None
        self._session: Optional[AsyncSession] = None

    async def connect(self) -> AsyncSession:
        if not self._engine:
            self._engine = create_async_engine(self._database_url, echo=False, future=True)
            self._session_maker = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        self._session = self._session_maker()
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None

    async def __aenter__(self) -> AsyncSession:
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
