import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

os.environ["IS_TESTING"] = "1"

from main import app
from database.connection import DatabaseConnection
from database.models import Base


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5437")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("TEST_DB_NAME", "pgwarden_test")

TEST_DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
ADMIN_DB_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/postgres"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine():
    """Creates the test database, sets up schemas, and provides a shared engine."""
    try:
        admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
        async with admin_engine.connect() as conn:
            result = await conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}'"))
            if not result.scalar():
                await conn.execute(text(f"CREATE DATABASE {DB_NAME}"))
        await admin_engine.dispose()
    except Exception as e:
        pytest.skip(f"Could not connect to Postgres: {e}")

    _engine = create_async_engine(TEST_DATABASE_URL)

    async with _engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS base CASCADE"))
        await conn.execute(text("DROP SCHEMA IF EXISTS collector CASCADE"))
        await conn.execute(text("DROP SCHEMA IF EXISTS metadata CASCADE"))
        await conn.execute(text("DROP SCHEMA IF EXISTS metric CASCADE"))

        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS timescaledb'))

        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS base"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS collector"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS metadata"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS metric"))

        await conn.run_sync(Base.metadata.create_all)

    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def cleanup(engine):
    """Truncates all tables after each test to guarantee isolation."""
    yield
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE {table.schema}."{table.name}" CASCADE'))


@pytest_asyncio.fixture
async def db_session(engine):
    """Provides a database session for each test."""
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(monkeypatch):
    """Provides an HTTP client with DatabaseConnection mocked to the test database."""
    def mock_init(self):
        self._database_url = TEST_DATABASE_URL
        self._engine = None
        self._session_maker = None
        self._session = None

    monkeypatch.setattr(DatabaseConnection, "__init__", mock_init)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client(client, db_session):
    """Provides an authenticated HTTP client with a committed test user."""
    from database.models.base import User
    from app.auth.services import create_access_token, pwd_context
    from datetime import timedelta

    user = User(
        email="auth_test@example.com",
        password=pwd_context.hash("password123"),
        name="Auth Test User",
        is_admin=True
    )
    db_session.add(user)
    await db_session.commit()

    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=15)
    )
    client.headers.update({"Authorization": f"Bearer {access_token}"})
    yield client
