"""Select the collector's local or central persistence backend."""

from __future__ import annotations

from pathlib import Path

from database.connection import DatabaseConnection
from database.sqlite_connection import SQLiteConnection
from utils import get_env_var

StorageConnection = DatabaseConnection | SQLiteConnection


def get_storage_backend() -> str:
    """Return the explicitly configured backend, defaulting to PostgreSQL."""
    backend = (get_env_var("COLLECTOR_STORAGE_BACKEND") or "postgresql").lower()
    if backend not in {"postgresql", "sqlite"}:
        raise ValueError("COLLECTOR_STORAGE_BACKEND must be postgresql or sqlite")
    return backend


def get_storage_connection() -> StorageConnection:
    """Create storage without changing connections to monitored PostgreSQLs."""
    if get_storage_backend() == "postgresql":
        return DatabaseConnection()

    path = get_env_var("COLLECTOR_SQLITE_PATH")
    if not path or path == ":memory:":
        raise ValueError("COLLECTOR_SQLITE_PATH must name a persistent SQLite file")
    return SQLiteConnection(Path(path).expanduser().resolve())
