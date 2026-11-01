"""Transactional SQLite storage for a standalone collector."""

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, AsyncIterator

from database.sqlite_cursor import SQLiteCursor, run_sqlite


def open_sqlite(path: Path) -> sqlite3.Connection:
    """Open an existing, migrated file with durable writes and foreign keys."""
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=rw",
        uri=True,
        check_same_thread=False,
        timeout=30,
    )
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("SELECT 1 FROM collector_server LIMIT 1")
    except Exception:
        connection.close()
        raise
    return connection


async def connect_sqlite(path: Path) -> sqlite3.Connection:
    """Close a newly opened connection if its caller is cancelled during setup."""
    task = asyncio.create_task(asyncio.to_thread(open_sqlite, path))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        connection = await task
        await run_sqlite(connection.close)
        raise


class SQLiteSession:
    """Hold the connection belonging to one collector storage transaction."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def cursor(self, row_factory: Any = None) -> SQLiteCursor:
        """Create a cursor with tuple or dictionary rows."""
        return SQLiteCursor(self._connection, as_dict=row_factory is not None)

    async def commit(self) -> None:
        """Persist the current transaction."""
        await run_sqlite(self._connection.commit)

    async def rollback(self) -> None:
        """Discard the current transaction."""
        await run_sqlite(self._connection.rollback)


class SQLiteConnection:
    """Serialize local writes while allowing a separate reader such as a sender."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._active: ContextVar = ContextVar("sqlite_storage_transaction")

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[SQLiteSession]:
        """Commit successful work and roll back errors or cancellation."""
        async with self._lock:
            connection = await connect_sqlite(self.path)
            session = SQLiteSession(connection)
            try:
                await run_sqlite(connection.execute, "BEGIN IMMEDIATE")
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise
            finally:
                await run_sqlite(connection.close)

    async def __aenter__(self) -> SQLiteSession:
        context = self.acquire()
        session = await context.__aenter__()
        self._active.set(context)
        return session

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self._active.get().__aexit__(exc_type, exc, traceback)
