"""
conftest.py – fixtures de teste para a API PGWarden.

Estratégia:
  • Cria um engine SQLAlchemy dedicado apontando para o banco de teste (pgwarden_test).
  • Faz monkey-patch da classe DatabaseConnection para que todos os routers que
    usam `async with DatabaseConnection() as conn:` recebam a sessão de teste
    dentro de uma transação que é revertida ao final de cada teste.
  • Expõe as fixtures `db_session`, `client` (sem autenticação) e `auth_client`
    (com JWT válido) para os testes de integração.
"""

import os
import pytest
import pytest_asyncio

from httpx import AsyncClient, ASGITransport
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

os.environ.setdefault("IS_TESTING", "1")
os.environ.setdefault("DB_HOST",     os.getenv("DB_HOST",     "localhost"))
os.environ.setdefault("DB_PORT",     os.getenv("DB_PORT",     "5437"))
os.environ.setdefault("DB_USER",     os.getenv("DB_USER",     "postgres"))
os.environ.setdefault("DB_PASSWORD", os.getenv("DB_PASSWORD", "postgres"))
os.environ.setdefault("DB_NAME",     os.getenv("TEST_DB_NAME","pgwarden_test"))
os.environ.setdefault("SECRET_KEY",  os.getenv("SECRET_KEY",  "test-secret-key-not-for-production"))

from database.models import Base          # noqa: E402  (also registers all submodels)
from database.models.base.user import User           # noqa: E402
import database.connection as _db_connection_module  # noqa: E402


_DB_URL = (
    f"postgresql+asyncpg://"
    f"{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
    f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}"
    f"/{os.environ['DB_NAME']}"
)

from sqlalchemy.pool import NullPool

_test_engine = create_async_engine(_DB_URL, echo=False, future=True, poolclass=NullPool)
_TestSessionMaker = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    """
    Yields a SQLAlchemy AsyncSession that wraps everything in a savepoint
    so that changes are rolled back after each test (no data leakage).
    """
    async with _test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        original_aenter = _db_connection_module.DatabaseConnection.__aenter__
        original_aexit  = _db_connection_module.DatabaseConnection.__aexit__

        async def _fake_aenter(self):
            return session

        async def _fake_aexit(self, *args):
            pass

        _db_connection_module.DatabaseConnection.__aenter__ = _fake_aenter
        _db_connection_module.DatabaseConnection.__aexit__  = _fake_aexit

        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
            _db_connection_module.DatabaseConnection.__aenter__ = original_aenter
            _db_connection_module.DatabaseConnection.__aexit__  = original_aexit


@pytest_asyncio.fixture
async def client(db_session):  # noqa: F811  (db_session patches the connection)
    from main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@pytest_asyncio.fixture
async def test_user(db_session):
    user = User(
        email="test@example.com",
        password=pwd_context.hash("password123"),
        name="Test User",
        is_admin=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def auth_client(client, test_user):
    resp = await client.post(
        "/v1/auth",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert resp.status_code == 200, f"auth failed: {resp.text}"
    token = resp.json()["access_token"]["token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client
