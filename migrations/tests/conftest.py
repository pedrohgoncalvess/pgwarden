import os

import pytest

import psycopg
from yoyo import get_backend, read_migrations


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5437")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = "pgwarden_migration_test"

@pytest.fixture(scope="session")
def db_url():
    """Returns the connection URL for the migration test database."""
    return f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

@pytest.fixture(scope="session")
def admin_conn():
    """Provides a connection to the 'postgres' database to manage the test database."""
    conn = psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        autocommit=True
    )
    yield conn
    conn.close()

@pytest.fixture(scope="session")
def setup_migration_db(admin_conn):
    """Creates the migration test database if it does not exist."""
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f"SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if not cur.fetchone():
                cur.execute(f"CREATE DATABASE {DB_NAME}")
    except Exception as e:
        pytest.skip(f"Could not connect to Postgres to setup migration tests: {e}")
    yield

@pytest.fixture
def backend(db_url):
    """Provides a Yoyo backend for the test database."""
    backend = get_backend(db_url)
    yield backend

@pytest.fixture
def migrations():
    """Reads all migrations from the sql directory."""
    migrations_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sql")
    return read_migrations(migrations_path)
